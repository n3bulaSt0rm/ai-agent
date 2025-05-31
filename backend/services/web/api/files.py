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
from PyPDF2 import PdfReader

from backend.core.config import settings
from backend.db.metadata import get_metadata_db
from backend.services.messaging import publish_message
from backend.utils.s3 import upload_to_s3, upload_to_s3_public, get_signed_url

router = APIRouter(prefix="/files", tags=["files"])

# Models for request/response
class FileUpdateRequest(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None
    keywords: Optional[Union[str, List[str]]] = None

class ProcessFileRequest(BaseModel):
    page_ranges: Optional[List[Dict[str, int]]] = None  # List of {start: int, end: int}

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    file_created_at: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None)
):
    """
    Upload a file to S3 and store metadata
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    try:
        # Generate unique identifier but keep original filename
        unique_id = str(uuid.uuid4())
        safe_filename = file.filename.replace(" ", "_").lower()
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Count pages in PDF
        pdf_pages = 0
        try:
            pdf = PdfReader(io.BytesIO(content))
            pdf_pages = len(pdf.pages)
        except Exception as e:
            print(f"Warning: Could not read PDF pages: {str(e)}")
        
        # Upload to S3 with public-read ACL
        s3_path = f"files/{unique_id}_{safe_filename}"
        s3_url = await upload_to_s3(content, s3_path)  # Keep original s3_url for internal use
        
        # Get direct public URL
        public_url = await upload_to_s3_public(content, s3_path)
        
        # Process keywords - simply use provided string directly
        keywords_str = keywords or ""
        # Clean up keywords string: remove extra spaces, ensure comma separation
        keywords_str = ",".join([k.strip() for k in keywords_str.split(',') if k.strip()])
        
        # Parse keywords into list for response
        keyword_list = [k.strip() for k in keywords_str.split(',') if k.strip()] if keywords_str else []
        
        # Create metadata
        metadata = {
            "original_extension": os.path.splitext(file.filename)[1],
            "content_type": file.content_type,
            "upload_timestamp": datetime.now().isoformat(),
            "uuid": unique_id,
            "keywords": keywords_str
        }
        
        # Store in database
        db = get_metadata_db()
        
        current_time = datetime.now().isoformat()
        
        file_id = db.add_pdf_file(
            filename=safe_filename,
            file_size=file_size,
            content_type=file.content_type or "application/pdf",
            s3_uri=s3_url,
            object_url=public_url,  # Use public URL here
            description=description,
            file_created_at=file_created_at or current_time,
            keywords=keywords_str,
            uuid=unique_id,
            pages=pdf_pages
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
            "s3_url": s3_url,
            "object_url": public_url,  # Include public URL in response
            "status": "pending_upload",
            "description": description,
            "keywords": keyword_list,
            "pages": pdf_pages,
            "type": "pdf",
            "uploadedBy": "admin"
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
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)")
):
    """
    Unified endpoint for listing all files with filtering, searching, and sorting
    """
    try:
        # Log request parameters for debugging
        params = dict(request.query_params)
        print(f"Files API params: {params}")
        
        # Initialize database connection
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
            # Generate signed URL for viewing
            view_url = get_signed_url(file_data["s3_uri"], expiration=3600)
            
            # Parse keywords if present
            keywords = []
            if file_data.get("keywords"):
                # Parse comma-separated string to list
                keywords = [k.strip() for k in file_data.get("keywords").split(',') if k.strip()]
                print(f"Processing file {file_data['id']} with keywords: {file_data.get('keywords')} -> {keywords}")
            
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
                "type": "pdf",
                "uuid": file_data.get("uuid", ""),
                "uploadedBy": file_data.get("uploaded_by", "admin"),
                "keywords": keywords,
                "pages_processed_range": file_data.get("pages_processed_range", ""),
                "link": view_url,
                "filename": file_data["filename"],
                "s3_uri": file_data["s3_uri"],
                "view_url": view_url
            }
            
            # Special handling for deleted files
            if file_data["status"] == "deleted":
                formatted_file["deletedDate"] = file_data.get("updated_at", file_data["upload_at"])
                formatted_file["deletedBy"] = file_data.get("uploaded_by", "admin")
            
            # Map status values to what frontend expects
            if formatted_file["status"] == "processed":
                formatted_file["status"] = "processed"
            elif formatted_file["status"] == "processing":
                formatted_file["status"] = "processing"
            elif formatted_file["status"] != "deleted":
                formatted_file["status"] = "pending_upload"
            
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
async def get_file_stats():
    """
    Get file statistics for dashboard
    """
    try:
        db = get_metadata_db()
        # Get total active files (not deleted)
        total_files = db.get_pdf_file_count(exclude_status="deleted")
        pending_files = db.get_pdf_file_count(status="pending")
        processing_files = db.get_pdf_file_count(status="processing")
        processed_files = db.get_pdf_file_count(status="processed")
        trash_files = db.get_pdf_file_count(status="deleted")
        
        return {
            "total": total_files,
            "pending": pending_files,
            "processing": processing_files,
            "processed": processed_files,
            "trash": trash_files
        }
    except Exception as e:
        print(f"Error getting file stats: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get file statistics: {str(e)}")

@router.get("/{file_id}")
async def get_file(file_id: int):
    """
    Get details of a specific file
    """
    try:
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Generate signed URL for viewing
        view_url = get_signed_url(file["s3_uri"], expiration=3600)
        
        # Parse keywords if present
        keywords = []
        if file.get("keywords"):
            # Parse comma-separated string to list
            keywords = [k.strip() for k in file.get("keywords").split(',') if k.strip()]
                
        # Format response to match frontend expectations
        formatted_file = {
            "id": file["id"],
            "title": file["filename"],
            "size": f"{round(file['file_size'] / 1024 / 1024, 2)} MB",
            "uploadAt": file["upload_at"],
            "status": file["status"],
            "pages": file["pages"] or 0,
            "type": "pdf",
            "uploadedBy": file.get("uploaded_by", "admin"),
            "description": file.get("description", ""),
            "fileCreatedAt": file.get("file_created_at", file["upload_at"]),
            "updatedAt": file.get("updated_at", file["upload_at"]),
            "link": view_url,
            "filename": file["filename"],
            "s3_uri": file["s3_uri"],
            "view_url": view_url,
            "keywords": keywords,
            "pages_processed_range": file.get("pages_processed_range")
        }
        
        # Map status values to what frontend expects
        if formatted_file["status"] == "processed":
            formatted_file["status"] = "processed"
        elif formatted_file["status"] == "processing":
            formatted_file["status"] = "processing"
        else:
            formatted_file["status"] = "pending_upload"
        
        return formatted_file
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get file: {str(e)}")

@router.post("/{file_id}/process")
async def process_file(file_id: int, process_request: Optional[ProcessFileRequest] = None):
    """
    Send a file for processing with optional page ranges
    """
    try:
        db = get_metadata_db()
        file = db.get_pdf_file(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
                
        if file["status"] == "processing":
            raise HTTPException(status_code=400, detail="File is already being processed")
        
        # Get total pages
        total_pages = file.get("pages", 0)
        
        # Get existing processed page ranges if any
        current_ranges = []
        if file.get("pages_processed_range"):
            try:
                current_ranges = json.loads(file["pages_processed_range"])
                if not isinstance(current_ranges, list):
                    current_ranges = []
            except:
                current_ranges = []
        
        # Determine page ranges to process
        page_ranges_to_process = []
        
        if process_request and process_request.page_ranges:
            # User specified page ranges
            page_ranges_to_process = process_request.page_ranges
            
            # Validate page ranges
            for page_range in page_ranges_to_process:
                if not isinstance(page_range, dict) or "start" not in page_range or "end" not in page_range:
                    raise HTTPException(status_code=400, detail="Invalid page range format. Expected {start: int, end: int}")
                
                start = page_range["start"]
                end = page_range["end"]
                
                if not isinstance(start, int) or not isinstance(end, int):
                    raise HTTPException(status_code=400, detail="Page range start and end must be integers")
                
                if start < 1 or end > total_pages or start > end:
                    raise HTTPException(status_code=400, 
                        detail=f"Invalid page range: {start}-{end}. Document has {total_pages} pages.")
                
                # Check if range overlaps with already processed ranges
                for processed_range in current_ranges:
                    p_start = processed_range["start"]
                    p_end = processed_range["end"]
                    
                    if (start <= p_end and end >= p_start):
                        raise HTTPException(status_code=400, 
                            detail=f"Page range {start}-{end} overlaps with already processed range {p_start}-{p_end}")
        else:
            # No ranges specified, process all pages that haven't been processed yet
            if not current_ranges and total_pages > 0:
                # Process entire document
                page_ranges_to_process = [{"start": 1, "end": total_pages}]
            elif total_pages > 0:
                # Find unprocessed ranges
                sorted_ranges = sorted(current_ranges, key=lambda r: r["start"])
                
                # Check from beginning of document
                if sorted_ranges[0]["start"] > 1:
                    page_ranges_to_process.append({"start": 1, "end": sorted_ranges[0]["start"] - 1})
                
                # Check between processed ranges
                for i in range(len(sorted_ranges) - 1):
                    if sorted_ranges[i]["end"] + 1 < sorted_ranges[i+1]["start"]:
                        page_ranges_to_process.append({
                            "start": sorted_ranges[i]["end"] + 1,
                            "end": sorted_ranges[i+1]["start"] - 1
                        })
                
                # Check end of document
                if sorted_ranges[-1]["end"] < total_pages:
                    page_ranges_to_process.append({"start": sorted_ranges[-1]["end"] + 1, "end": total_pages})
        
        if not page_ranges_to_process:
            return {"message": "No page ranges to process", "status": file["status"]}
        
        # Update status to processing
        db.update_pdf_status(file_id, "processing")
        
        # Get keywords from the database
        keywords_str = file.get("keywords")
        keywords = []
        if keywords_str:
            # Convert comma-separated string to list
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                
        file_uuid = file.get("uuid")
        file_created_at = file.get("file_created_at")
        
        # Update processed page ranges
        new_processed_ranges = current_ranges + page_ranges_to_process
        db.update_pdf_status(file_id, "processing", pages_processed_range=json.dumps(new_processed_ranges))
        
        # Send processing requests for each page range
        for page_range in page_ranges_to_process:
            # Send processing request via messaging service
            message_data = {
                "file_id": file_uuid,
                "file_path": file["object_url"] if file.get("object_url") else file["s3_uri"],  # Use object_url if available
                "file_created_at": file_created_at,
                "keywords": keywords,
                "action": "process",
                "page_range": page_range
            }
            
            await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
        
        return {
            "message": f"File {file_id} sent for processing",
            "status": "processing",
            "page_ranges": page_ranges_to_process
        }
    except HTTPException:
        raise
    except Exception as e:
        # Revert status on error
        try:
            db = get_metadata_db()
            db.update_pdf_status(file_id, "pending", str(e))
        except:
            pass
        
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

@router.delete("/{file_id}")
async def delete_file(file_id: int):
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
        
        # Update status to deleted
        db.update_pdf_status(file_id, "deleted", previous_status=previous_status)
        
        # Get UUID from file
        file_uuid = file.get("uuid")
        
        if file_uuid:
            # Send message to update vectors in Qdrant (simplified message format)
            message_data = {
                "file_id": file_uuid,
                "action": "delete"
            }
            
            await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
        
        return {
            "message": f"File {file_id} marked as deleted",
            "status": "deleted",
            "previous_status": previous_status
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@router.post("/{file_id}/restore")
async def restore_file(file_id: int):
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
        
        # Restore to previous status if available
        new_status = file.get("previous_status") or "pending"
        
        # Update status
        db.update_pdf_status(file_id, new_status)
        
        # Get UUID from file
        file_uuid = file.get("uuid")
        
        if file_uuid:
            # Send message to restore vectors in Qdrant (simplified message format)
            message_data = {
                "file_id": file_uuid,
                "file_path": file["object_url"] if file.get("object_url") else file["s3_uri"],  # Use object_url if available
                "action": "restore"
            }
            
            await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
        
        return {
            "message": f"File {file_id} restored to {new_status} status",
            "status": new_status
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore file: {str(e)}")

@router.put("/update/{file_id}")
async def update_file(
    file_id: int,
    file_update: FileUpdateRequest
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
            
            # Send message to processing service about keyword update
            file_uuid = file.get("uuid")
            file_path = file.get("object_url") if file.get("object_url") else file.get("s3_uri")  # Use object_url if available
            
            if file_uuid:
                # Get file_created_at for consistency 
                file_created_at = file.get("file_created_at")
                
                # Send message to update keywords in processing service
                message_data = {
                    "file_id": file_uuid,
                    "file_path": file_path,
                    "keywords": keyword_list,
                    "file_created_at": file_created_at,
                    "action": "update_keywords"
                }
                
                await publish_message(settings.PDF_PROCESSING_TOPIC, message_data)
                
                # Log success
                print(f"Message sent to processing service for file {file_id} with keywords: {keyword_list}")
        
        return {
            "file_id": file_id,
            "updates": updates,
            "message": "File updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}") 