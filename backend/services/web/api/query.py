from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from backend.core.config import settings
from backend.db.metadata import get_metadata_db
from backend.db.vector_store import get_vector_store

# Configure logging
logger = logging.getLogger("web_service.api.query")

router = APIRouter(prefix="/query", tags=["query"])

@router.get("/")
async def query_documents(
    q: str = Query(..., description="Query string to search for"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of results to return"),
    filter_by_file_id: Optional[int] = Query(None, description="Filter by file ID"),
    include_deleted: bool = Query(False, description="Include deleted documents in search")
):
    """
    Query documents using semantic search
    """
    try:
        # Get metadata DB to fetch file information
        metadata_db = get_metadata_db()
        
        # Get vector store for searching
        vector_store = get_vector_store()
        
        # Prepare filters
        filters = {}
        
        # Filter by file ID if provided
        if filter_by_file_id is not None:
            # Get file metadata to extract UUID
            file = metadata_db.get_pdf_file(filter_by_file_id)
            if not file:
                raise HTTPException(status_code=404, detail=f"File with ID {filter_by_file_id} not found")
            
            # Extract UUID from metadata
            metadata = file.get("metadata", {})
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)
                
            file_uuid = metadata.get("uuid")
            if not file_uuid:
                raise HTTPException(status_code=400, detail=f"File with ID {filter_by_file_id} does not have a UUID")
            
            filters["uuid"] = file_uuid
        
        # Handle deleted filter
        if not include_deleted:
            filters["is_deleted"] = False
        
        # Perform search
        results = await vector_store.search(
            query_text=q,
            limit=limit,
            filters=filters
        )
        
        # Process results
        processed_results = []
        for result in results:
            # Get document metadata
            metadata = result.get("metadata", {})
            
            # Get file information if available
            file_info = None
            if "file_id" in metadata:
                file = metadata_db.get_pdf_file(metadata["file_id"])
                if file:
                    file_info = {
                        "id": file["id"],
                        "filename": file["filename"],
                        "upload_date": file["upload_at"],
                        "status": file["status"]
                    }
            
            # Add to processed results
            processed_results.append({
                "content": result.get("content", ""),
                "metadata": metadata,
                "file": file_info,
                "score": result.get("score", 0),
                "page_number": metadata.get("page", 0),
                "chunk_index": metadata.get("chunk_index", 0)
            })
        
        return {
            "query": q,
            "results": processed_results,
            "count": len(processed_results),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@router.get("/files/{file_id}")
async def query_file_content(
    file_id: int,
    q: Optional[str] = Query(None, description="Query string to search within the file"),
    page: Optional[int] = Query(None, description="Page number to retrieve"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of chunks to return")
):
    """
    Query content from a specific file
    """
    try:
        # Get metadata DB to fetch file information
        metadata_db = get_metadata_db()
        
        # Get file metadata
        file = metadata_db.get_pdf_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")
        
        # Check if file is deleted
        if file["status"] == "deleted":
            raise HTTPException(status_code=400, detail="File is deleted")
        
        # Extract UUID from metadata
        metadata = file.get("metadata", {})
        if isinstance(metadata, str):
            import json
            metadata = json.loads(metadata)
            
        file_uuid = metadata.get("uuid")
        if not file_uuid:
            raise HTTPException(status_code=400, detail=f"File with ID {file_id} does not have a UUID")
        
        # Get vector store for searching
        vector_store = get_vector_store()
        
        # Prepare filters
        filters = {
            "uuid": file_uuid,
            "is_deleted": False
        }
        
        # Add page filter if specified
        if page is not None:
            filters["page"] = page
        
        # Perform search or retrieval
        if q:
            # Semantic search within the file
            results = await vector_store.search(
                query_text=q,
                limit=limit,
                filters=filters
            )
        else:
            # Retrieve content in order
            results = await vector_store.get_documents(
                limit=limit,
                filters=filters,
                sort_by={"key": "chunk_index", "order": "asc"}  # Sort by chunk index for proper order
            )
        
        # Process results
        processed_results = []
        for result in results:
            # Get document metadata
            metadata = result.get("metadata", {})
            
            # Add to processed results
            processed_results.append({
                "content": result.get("content", ""),
                "page_number": metadata.get("page", 0),
                "chunk_index": metadata.get("chunk_index", 0),
                "score": result.get("score", 0) if q else None
            })
        
        return {
            "file_id": file_id,
            "filename": file["filename"],
            "query": q,
            "page": page,
            "results": processed_results,
            "count": len(processed_results),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in file query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File query failed: {str(e)}")

@router.get("/stats")
async def get_query_stats():
    """
    Get statistics about indexed documents
    """
    try:
        # Get metadata DB
        metadata_db = get_metadata_db()
        
        # Get vector store
        vector_store = get_vector_store()
        
        # Get stats from vector store
        vector_stats = await vector_store.get_stats()
        
        # Get file stats from metadata DB
        processed_files = metadata_db.get_pdf_file_count(status="completed")
        pending_files = metadata_db.get_pdf_file_count(status="pending")
        processing_files = metadata_db.get_pdf_file_count(status="processing")
        deleted_files = metadata_db.get_pdf_file_count(status="deleted")
        error_files = metadata_db.get_pdf_file_count(status="error")
        
        return {
            "vector_store": {
                "total_documents": vector_stats.get("total_documents", 0),
                "total_files": vector_stats.get("total_files", 0),
                "total_pages": vector_stats.get("total_pages", 0),
                "dimensions": vector_stats.get("dimensions", 0)
            },
            "files": {
                "processed": processed_files,
                "pending": pending_files,
                "processing": processing_files,
                "deleted": deleted_files,
                "error": error_files,
                "total": processed_files + pending_files + processing_files + deleted_files + error_files
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}") 