from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional, Union
import os
import uuid
from datetime import datetime
from pydantic import BaseModel
import json
import traceback
import io
import filetype
from PyPDF2 import PdfReader

from backend.core.config import settings
from backend.db.metadata import get_metadata_db
from backend.services.messaging import publish_message
from backend.utils.s3 import upload_to_s3, upload_to_s3_public, get_signed_url
from backend.services.web.api.auth import get_admin_user, get_admin_or_manager_user

router = APIRouter(prefix="/files", tags=["files"])

class FileUpdateRequest(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None
    keywords: Optional[Union[str, List[str]]] = None
    file_created_at: Optional[str] = None

class ProcessFileRequest(BaseModel):
    page_ranges: Optional[List[str]] = None 

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    file_created_at: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    current_user: dict = Depends(get_admin_or_manager_user)
):
    """
    Upload a file to S3 and store metadata
    """
    content = await file.read()
    content_type = ""
    detected_type = filetype.guess(content)
    if detected_type is not None:
        content_type = detected_type.mime
    else:
        # Nếu không phát hiện được type bằng magic bytes, kiểm tra phần mở rộng file
        filename_lower = file.filename.lower()
        if filename_lower.endswith('.txt'):
            content_type = 'text/plain'
            print(f"File type detected from extension: {file.filename} -> {content_type}")
        else:
            print(f"Error: Could not detect file type: {file.filename}")

    
    allowed_mime_types = []
    try:
        mime_types_file = os.path.join(os.path.dirname(__file__), '../../../../mime_types.txt')
        with open(mime_types_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    allowed_mime_types.append(line)
    except Exception as e:
        print(f"Warning: Could not load mime_types.txt: {e}")
        allowed_mime_types = ['application/pdf', 'text/plain']
    
    if content_type not in allowed_mime_types:
        raise HTTPException(
            status_code=400, 
            detail=f"File type not supported. Allowed types: {', '.join(allowed_mime_types)}"
        )
    
    try:
        unique_id = str(uuid.uuid4())
        safe_filename = file.filename.replace(" ", "_").lower()
        
        file_size = len(content)
        
        file_pages = 0
        
        if content_type == 'application/pdf':
            try:
                pdf = PdfReader(io.BytesIO(content))
                file_pages = len(pdf.pages)
            except Exception as e:
                print(f"Warning: Could not read PDF pages: {str(e)}")
                file_pages = 1 
        elif content_type == 'text/plain':
            file_pages = 1
        
        # Upload to S3 with public-read ACL
        s3_path = f"files/{unique_id}_{safe_filename}"
        
        public_url = await upload_to_s3_public(content, s3_path)
        
        keywords_str = keywords or ""        
        if keywords_str:
            keywords_str = ",".join([k.strip() for k in keywords_str.split(',') if k.strip()])
        
        keyword_list = [k.strip() for k in keywords_str.split(',') if k.strip()] if keywords_str else []
        
        db = get_metadata_db()
        
        current_time = datetime.now().isoformat()
        
        file_id = db.add_pdf_file(
            filename=safe_filename,
            file_size=file_size,
            content_type=content_type,  
            object_url=public_url,  
            description=description,
            file_created_at=file_created_at,
            keywords=keywords_str,
            uuid=unique_id,
            pages=file_pages,
            uploaded_by=current_user['username']
        )
        
        # Format response to match frontend expectations
        return {
            "id": file_id,
            "title": file.filename,
            "filename": safe_filename,
            "size": f"{round(file_size / 1024 / 1024, 2)} MB",
            "uploadAt": current_time,
            "fileCreatedAt": file_created_at or current_time,
            "updatedAt": current_time,
            "uuid": unique_id,
            "object_url": public_url,  
            "status": "pending",  
            "description": description,
            "keywords": keyword_list,
            "pages": file_pages,
            "type": "txt" if content_type == "text/plain" else "pdf",
            "uploadedBy": current_user['username']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/")
async def list_files(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="File status (pending, processing, processed, deleted)"),
    query: Optional[str] = Query(None, description="Search query for title or description"),
    sort_by: Optional[str] = Query(None, description="Field to sort by (size, uploadAt, updatedAt, fileCreatedAt)"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc, newest, oldest, largest, smallest)"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    current_user: dict = Depends(get_admin_or_manager_user)
):
    try:
        
        db = get_metadata_db()
        
        # Default files query for non-deleted files when status is not specified
        if status is None and not any([query, date]):
            status = 'active'  # Custom value to get non-deleted files
        
        # Process database results if they exist
        files = []
        total_count = 0
        
        try:
            # Handle different query scenarios:
            
            # 1. Search by query text
            if query:
                files = db.search_pdf_files(query, limit=limit, offset=offset, status=status)
                total_count = len(files)
                print(f"Search results: Found {len(files)} files matching '{query}'")
                if files:
                    # Log keywords from first result for debugging
                    print(f"First result keywords (raw): {files[0].get('keywords')}")
                
            # 2. Filter by date
            elif date:
                # Convert date string to expected format
                filter_date = date
                
                # Query files matching the date
                if status == 'deleted':
                    # For deleted files, the updated_at field represents the deletion date
                    query_sql = '''
                    SELECT * FROM files_management 
                    WHERE ((date(upload_at) = ? OR date(file_created_at) = ? OR date(updated_at) = ?) AND status = "deleted")
                    '''
                else:
                    query_sql = '''
                    SELECT * FROM files_management 
                    WHERE (date(upload_at) = ? OR date(file_created_at) = ? OR date(updated_at) = ?)
                    '''
                    
                    # Add status filter if specified
                    if status == 'active':
                        query_sql += ' AND status != "deleted"'
                    elif status:
                        query_sql += f' AND status = "{status}"'
                
                # Add sorting and pagination
                query_sql += '''
                ORDER BY upload_at DESC
                LIMIT ? OFFSET ?
                '''
                
                # Execute query with all parameters
                cursor = db.conn.execute(
                    query_sql, 
                    (filter_date, filter_date, filter_date, limit, offset)
                )
                
                # Parse results
                for row in cursor:
                    file_data = dict(row)
                    files.append(file_data)
                
                # Get total count
                if status == 'deleted':
                    count_query = '''
                    SELECT COUNT(*) FROM files_management 
                    WHERE ((date(upload_at) = ? OR date(file_created_at) = ? OR date(updated_at) = ?) AND status = "deleted")
                    '''
                else:
                    count_query = '''
                    SELECT COUNT(*) FROM files_management 
                    WHERE (date(upload_at) = ? OR date(file_created_at) = ? OR date(updated_at) = ?)
                    '''
                    
                    # Add same status filter as the main query
                    if status == 'active':
                        count_query += ' AND status != "deleted"'
                    elif status:
                        count_query += f' AND status = "{status}"'
                
                cursor = db.conn.execute(count_query, (filter_date, filter_date, filter_date))
                total_count = cursor.fetchone()[0]
                
            # 3. Sort by field
            elif sort_by:
                # Map frontend sort fields to database fields
                field_mapping = {
                    "size": "file_size",
                    "uploadAt": "upload_at",
                    "updatedAt": "updated_at",
                    "fileCreatedAt": "file_created_at",
                    "deletedDate": "updated_at"  # For trash, deletedDate maps to updated_at
                }
                
                # Map sort order to SQL direction
                actual_sort_order = sort_order
                if sort_order in ["newest", "largest"]:
                    actual_sort_order = "desc"
                elif sort_order in ["oldest", "smallest"]:
                    actual_sort_order = "asc"
                
                db_field = field_mapping.get(sort_by)
                
                # If field not found in mapping, use upload_at as default
                if not db_field:
                    db_field = "upload_at"
                    print(f"Warning: Unknown sort field '{sort_by}', using 'upload_at' instead.")
                
                # Build query with sorting and status filter
                query_sql = 'SELECT * FROM files_management WHERE '
                
                # Add status filter
                if status == 'deleted':
                    query_sql += 'status = "deleted"'
                elif status == 'active':
                    query_sql += 'status != "deleted"'
                elif status:
                    query_sql += f'status = "{status}"'
                else:
                    query_sql += '1=1'  # No status filter
                
                # Add sorting and pagination
                query_sql += f'''
                ORDER BY {db_field} {actual_sort_order.upper()}
                LIMIT ? OFFSET ?
                '''
                
                # Execute the query
                cursor = db.conn.execute(query_sql, (limit, offset))
                
                # Parse results
                for row in cursor:
                    file_data = dict(row)
                    files.append(file_data)
                
                # Get total count with same status filter
                count_query = 'SELECT COUNT(*) FROM files_management WHERE '
                
                if status == 'deleted':
                    count_query += 'status = "deleted"'
                elif status == 'active':
                    count_query += 'status != "deleted"'
                elif status:
                    count_query += f'status = "{status}"'
                else:
                    count_query += '1=1'
                
                cursor = db.conn.execute(count_query)
                total_count = cursor.fetchone()[0]
                
            # 4. Default list with status filter
            else:
                # Translate 'active' to exclude deleted files
                if status == 'active':
                    files = db.get_pdf_files(limit=limit, offset=offset, exclude_status="deleted")
                    total_count = db.get_pdf_file_count(exclude_status="deleted")
                else:
                    files = db.get_pdf_files(limit=limit, offset=offset, status=status)
                    total_count = db.get_pdf_file_count(status=status)
                
        except Exception as db_error:
            print(f"Database error: {db_error}")
            traceback_str = traceback.format_exc()
            print(f"Traceback: {traceback_str}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
            
        # Format files for frontend
        response_files = []
        for file_data in files:
            # Parse keywords if present
            keywords = []
            raw_keywords = file_data.get("keywords", "")
            
            if raw_keywords:
                # Parse comma-separated string to list
                keywords = [k.strip() for k in raw_keywords.split(',') if k.strip()]            
            # Format for frontend
            formatted_file = {
                "id": file_data["id"],
                "title": file_data["filename"],
                "size": f"{round(file_data['file_size'] / 1024 / 1024, 2)} MB",
                "uploadAt": file_data["upload_at"],
                "fileCreatedAt": file_data.get("file_created_at", file_data["upload_at"]),
                "updatedAt": file_data.get("updated_at", file_data["upload_at"]),
                "status": file_data["status"],
                "description": file_data.get("description", ""),
                "pages": file_data.get("pages", 0),
                "type": "txt" if file_data.get("content_type") == "text/plain" else "pdf",
                "uuid": file_data.get("uuid", ""),
                "uploadedBy": file_data.get("uploaded_by", "admin"),
                "keywords": keywords,
                "pages_processed_range": file_data.get("pages_processed_range", ""),
                "link": file_data["object_url"],
                "filename": file_data["filename"],
                "view_url": file_data["object_url"]
            }
            
            # Special handling for deleted files
            if file_data["status"] == "deleted":
                formatted_file["deletedDate"] = file_data.get("updated_at", file_data["upload_at"])
                formatted_file["deletedBy"] = file_data.get("uploaded_by", "admin")
            
            response_files.append(formatted_file)
        
        # Return response with pagination info
        response = {
            "files": response_files,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
        
        # Add filter-specific data to response
        if query:
            response["query"] = query
        if date:
            response["filter_date"] = date
        if sort_by:
            response["sort_by"] = sort_by
            response["sort_order"] = sort_order
            
        return response
            
    except Exception as e:
        print(f"Error listing files: {str(e)}")
        traceback_str = traceback.format_exc()
        print(f"Traceback: {traceback_str}")
        return JSONResponse(
            status_code=500, 
            content={"detail": f"Failed to list files: {str(e)}"}
        )

@router.get("/stats")
async def get_file_stats(current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Get file statistics for dashboard including storage usage
    """
    try:
        # Get metadata DB
        db = get_metadata_db()
        
        # Get file stats by status
        total_files = db.get_pdf_file_count(exclude_status="deleted")
        pending_files = db.get_pdf_file_count(status="pending")
        processing_files = db.get_pdf_file_count(status="processing")
        processed_files = db.get_pdf_file_count(status="processed")
        trash_files = db.get_pdf_file_count(status="deleted")
        
        # Calculate total storage used (in bytes)
        cursor = db.conn.execute("SELECT SUM(file_size) as total_size FROM files_management")
        row = cursor.fetchone()
        total_size_bytes = row["total_size"] if row["total_size"] is not None else 0
        
        # Convert to MB with 2 decimal precision
        total_size_mb = round(total_size_bytes / (1024 * 1024), 2)
        
        # Get storage limit from settings (default 1000MB if not set)
        storage_limit_mb = getattr(settings, "STORAGE_LIMIT_MB", 1000)
        
        # Calculate percentage
        storage_percentage = round((total_size_mb / storage_limit_mb) * 100) if storage_limit_mb > 0 else 0
        
        # Format the response
        return {
            "total": total_files,
            "pending": pending_files,
            "processing": processing_files,
            "processed": processed_files,
            "trash": trash_files,
            "storage": {
                "used_mb": total_size_mb,
                "limit_mb": storage_limit_mb,
                "percentage": storage_percentage
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error getting file stats: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get file statistics: {str(e)}")

@router.get("/{file_id}")
async def get_file(file_id: int, current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Get details of a specific file
    """
    try:
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Parse keywords if present
        keywords = []
        raw_keywords = file.get("keywords", "")
        print(f"Raw keywords from DB for file {file_id}: '{raw_keywords}'")
        
        if raw_keywords:
            # Parse comma-separated string to list
            keywords = [k.strip() for k in raw_keywords.split(',') if k.strip()]
            print(f"Processing file {file_id} with keywords: '{raw_keywords}' -> {keywords}")
                
        # Format response to match frontend expectations
        formatted_file = {
            "id": file["id"],
            "title": file["filename"],
            "size": f"{round(file['file_size'] / 1024 / 1024, 2)} MB",
            "uploadAt": file["upload_at"],
            "status": file["status"],
            "pages": file["pages"] or 0,
            "type": "txt" if file.get("content_type") == "text/plain" else "pdf",
            "uploadedBy": file.get("uploaded_by", "admin"),
            "description": file.get("description", ""),
            "fileCreatedAt": file.get("file_created_at", file["upload_at"]),
            "updatedAt": file.get("updated_at", file["upload_at"]),
            "link": file["object_url"],
            "filename": file["filename"],
            "view_url": file["object_url"],
            "keywords": keywords,
            "pages_processed_range": file.get("pages_processed_range")
        }
        
        
        return formatted_file
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get file: {str(e)}")

@router.post("/{file_id}/process")
async def process_file(file_id: int, process_request: Optional[ProcessFileRequest] = None, current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Send a file for processing with optional page ranges
    """
    try:
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
                
        if file["status"] == "processing" or file["status"] == "preparing":
            raise HTTPException(status_code=400, detail="File is already being processed")
            
        if file["status"] == "processed":
            return {"message": "File has already been processed", "status": "processed"}
        
        total_pages = file.get("pages", 0)
        
        current_ranges = []
        if file.get("pages_processed_range"):
            try:
                current_ranges = json.loads(file["pages_processed_range"])
                if not isinstance(current_ranges, list):
                    current_ranges = []
            except:
                current_ranges = []
        
        page_ranges_to_process = []
        
        if process_request and process_request.page_ranges:
            # User specified page ranges as strings (e.g. "1-5")
            for range_str in process_request.page_ranges:
                try:
                    # Validate format
                    if not isinstance(range_str, str) or "-" not in range_str:
                        raise HTTPException(status_code=400, 
                            detail=f"Invalid page range format: {range_str}. Expected format: 'start-end'")
                    
                    # Parse range
                    start, end = map(int, range_str.split('-'))
                    
                    # Validate range
                    if start < 1 or (total_pages > 0 and end > total_pages) or start > end:
                        raise HTTPException(status_code=400, 
                            detail=f"Invalid page range: {range_str}. Document has {total_pages} pages.")
                    
                    # Check for overlap with existing ranges
                    for processed_range in current_ranges:
                        try:
                            p_start, p_end = map(int, processed_range.split('-'))
                            
                            if (start <= p_end and end >= p_start):
                                raise HTTPException(status_code=400, 
                                    detail=f"Page range {range_str} overlaps with already processed range {processed_range}")
                        except ValueError:
                            # Skip invalid ranges
                            continue
                    
                    # Add to list of ranges to process
                    page_ranges_to_process.append(range_str)
                except ValueError:
                    raise HTTPException(status_code=400, 
                        detail=f"Invalid page range format: {range_str}. Expected format: 'start-end' with numeric values")
        else:
            # No ranges specified, process all pages that haven't been processed yet
            if not current_ranges and total_pages > 0:
                # Process entire document
                page_ranges_to_process = [f"1-{total_pages}"]
            elif total_pages > 0:
                # Find unprocessed ranges
                # Extract and sort all processed page numbers
                processed_pages = set()
                for range_str in current_ranges:
                    try:
                        start, end = map(int, range_str.split('-'))
                        for page in range(start, end + 1):
                            processed_pages.add(page)
                    except ValueError:
                        # Skip invalid ranges
                        continue
                
                # Find unprocessed pages
                unprocessed = []
                current_start = None
                
                for page in range(1, total_pages + 1):
                    if page not in processed_pages:
                        if current_start is None:
                            current_start = page
                    elif current_start is not None:
                        # End of a range
                        unprocessed.append(f"{current_start}-{page-1}")
                        current_start = None
                
                # Check if we have an open range at the end
                if current_start is not None:
                    unprocessed.append(f"{current_start}-{total_pages}")
                
                page_ranges_to_process = unprocessed
        
        if not page_ranges_to_process:
            return {"message": "No page ranges to process", "status": file["status"]}
        
        db.update_pdf_status(file_id, "preparing")
        
        keywords_str = file.get("keywords", "")
                
        file_uuid = file.get("uuid")
        file_created_at = file.get("file_created_at")
        
        print(f"Preparing to process file {file_id} with ranges: {page_ranges_to_process}")

        for page_range in page_ranges_to_process:
            message_data = {
                "file_id": file_uuid,
                "file_path": file["object_url"],
                "file_created_at": file_created_at,
                "keywords": keywords_str,
                "content_type": file.get("content_type", "application/pdf"),  
                "action": "process",
                "page_range": page_range,  
                "webhook_url": f"{settings.API_BASE_URL}/api/webhook/status-update"
            }
            
            await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
        

        return {
            "message": f"File {file_id} sent for processing",
            "status": "preparing",
            "page_ranges": page_ranges_to_process
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            db = get_metadata_db()
            db.update_pdf_status(file_id, "pending")
        except Exception as rollback_error:
            print(f"Error rolling back status: {rollback_error}")
        
        print(f"Error processing file: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

@router.delete("/{file_id}")
async def delete_file(file_id: int, current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Soft delete a file and its metadata
    """
    try:
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
            
        if file["status"] == "deleted":
            raise HTTPException(status_code=400, detail="File is already deleted")
        
        # Save current status for potential restore
        previous_status = file["status"]
        
        # Update status to deleting (not directly to deleted)
        db.update_pdf_status(file_id, "deleting", previous_status=previous_status)
        
        # Get UUID from file
        file_uuid = file.get("uuid")
        
        if file_uuid:
            # Send message to update vectors in Qdrant (simplified message format)
            message_data = {
                "file_id": file_uuid,
                "action": "delete",
                "webhook_url": f"{settings.API_BASE_URL}/api/webhook/status-update"
            }
            
            await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
        
        return {
            "message": f"File {file_id} is being moved to trash",
            "status": "deleting",
            "previous_status": previous_status
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@router.post("/{file_id}/restore")
async def restore_file(file_id: int, current_user: dict = Depends(get_admin_or_manager_user)):
    """
    Restore a previously deleted file
    """
    try:
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
            
        if file["status"] != "deleted":
            raise HTTPException(status_code=400, detail="File is not deleted")
        
        # Get previous status if available for future update through webhook
        new_status = "restoring"
        previous_status = file.get("previous_status") or "pending"
        
        # Update status to restoring first
        db.update_pdf_status(file_id, new_status, previous_status=previous_status)
        
        # Get UUID from file
        file_uuid = file.get("uuid")
        
        if file_uuid:
            # Send message to restore vectors in Qdrant (simplified message format)
            message_data = {
                "file_id": file_uuid,
                "file_path": file["object_url"],
                "action": "restore",
                "previous_status": previous_status, 
                "webhook_url": f"{settings.API_BASE_URL}/api/webhook/status-update"
            }
            
            await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
        
        return {
            "message": f"File {file_id} restoration in progress",
            "status": new_status,
            "target_status": previous_status
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore file: {str(e)}")

@router.put("/update/{file_id}")
async def update_file(
    file_id: int,
    file_update: FileUpdateRequest,
    current_user: dict = Depends(get_admin_or_manager_user)
):
    """
    Update file metadata
    """
    try:
        print(f"Received update request for file {file_id}: {file_update}")
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
                
        updates = {}
        should_publish_message = file["status"] == "processed"
        
        # Update description if provided
        if file_update.description is not None:
            with db.conn:
                db.conn.execute(
                    "UPDATE files_management SET description = ?, updated_at = ? WHERE id = ?",
                    (file_update.description, datetime.now().isoformat(), file_id)
                )
                
            updates["description"] = file_update.description
        
        # Update status if provided
        if file_update.status is not None:
            valid_statuses = ["pending", "processing", "processed", "error", "deleted"]
            
            if file_update.status not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
                
            db.update_pdf_status(file_id, file_update.status)
            updates["status"] = file_update.status
            
            # Update should_publish_message if status was changed to processed
            if file_update.status == "processed":
                should_publish_message = True

        # Update file_created_at if provided
        if file_update.file_created_at is not None:
            with db.conn:
                db.conn.execute(
                    "UPDATE files_management SET file_created_at = ?, updated_at = ? WHERE id = ?",
                    (file_update.file_created_at, datetime.now().isoformat(), file_id)
                )
                
            updates["file_created_at"] = file_update.file_created_at
            
            # Send message to processing service if file is processed
            if should_publish_message:
                file_uuid = file.get("uuid")
                file_path = file.get("object_url")
                
                if file_uuid:
                    # Get keywords for consistency
                    keywords_str = file.get("keywords", "")
                    
                    # Send message to update file_created_at in processing service
                    message_data = {
                        "file_id": file_uuid,
                        "file_path": file_path,
                        "keywords": keywords_str,
                        "file_created_at": file_update.file_created_at,
                        "action": "update_metadata"
                    }
                    
                    await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
                    
                    print(f"Message sent to processing service for file {file_id} with updated file_created_at: {file_update.file_created_at}")

        # Update keywords if provided
        if file_update.keywords is not None:
            print(f"Updating keywords for file {file_id}: {file_update.keywords}")
            
            if isinstance(file_update.keywords, list):
                # Convert list to comma-separated string
                keywords_str = ','.join(file_update.keywords)
            else:
                # Already a string, normalize it
                keywords_str = ','.join([k.strip() for k in file_update.keywords.split(',') if k.strip()])
                
            print(f"Keywords string: {keywords_str}")
            
            # Update keywords in database
            with db.conn:
                db.conn.execute(
                    "UPDATE files_management SET keywords = ?, updated_at = ? WHERE id = ?",
                    (keywords_str, datetime.now().isoformat(), file_id)
                )
            
            # Convert string back to list for consistent response
            keyword_list = [k.strip() for k in keywords_str.split(',') if k.strip()] if keywords_str else []
            updates["keywords"] = keyword_list
            
            # Send message to processing service only if status is processed
            if should_publish_message:
                file_uuid = file.get("uuid")
                file_path = file.get("object_url")
                
                if file_uuid:
                    # Get file_created_at for consistency 
                    file_created_at = file_update.file_created_at or file.get("file_created_at")
                    
                    # Send message to update keywords in processing service
                    message_data = {
                        "file_id": file_uuid,
                        "file_path": file_path,
                        "keywords": keywords_str,  # Send the raw keywords string
                        "file_created_at": file_created_at,
                        "action": "update_keywords"
                    }
                    
                    await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
                    
                    # Log success
                    print(f"Message sent to processing service for file {file_id} with keywords: {keywords_str}")
            else:
                print(f"Skipping publish message for file {file_id} as status is not 'processed'")
        
        return {
            "file_id": file_id,
            "updates": updates,
            "message": "File updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}") 