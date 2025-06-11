from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import logging
from typing import Optional

from backend.core.config import settings

router = APIRouter(prefix="/search", tags=["search"])

logger = logging.getLogger(__name__)

class SearchRequest(BaseModel):
    text: str

class SearchResponse(BaseModel):
    status: str
    response: str
    timestamp: Optional[str] = None

@router.post("/intelligent")
async def intelligent_search(request: SearchRequest):
    """
    Intelligent document search using AI processing
    
    Args:
        request: SearchRequest containing the text to search
        
    Returns:
        SearchResponse with AI-generated response
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Search text is required")
        
        # URL của processing service
        processing_service_url = f"http://localhost:{settings.PROCESSING_PORT}/process-text"
        
        # Prepare request data for processing service
        processing_request = {
            "text": request.text.strip()
        }
        
        logger.info(f"Forwarding search request to processing service: {processing_service_url}")
        
        # Call processing service
        async with httpx.AsyncClient(timeout=180.0) as client:  # 3 minutes timeout
            response = await client.post(
                processing_service_url,
                json=processing_request
            )
            
            if response.status_code != 200:
                logger.error(f"Processing service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Processing service error: {response.text}"
                )
            
            # Parse response from processing service
            result = response.json()
            
            # Return formatted response
            return SearchResponse(
                status=result.get("status", "success"),
                response=result.get("response", ""),
                timestamp=result.get("timestamp")
            )
            
    except httpx.TimeoutException:
        logger.error("Timeout when calling processing service")
        raise HTTPException(
            status_code=504,
            detail="Search request timed out. Please try again with a shorter query."
        )
    except httpx.ConnectError:
        logger.error("Cannot connect to processing service")
        raise HTTPException(
            status_code=503,
            detail="Processing service is currently unavailable. Please try again later."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in intelligent search: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/health")
async def search_health():
    """Health check for search service"""
    try:
        # Test connection to processing service
        processing_service_url = f"http://localhost:{settings.PROCESSING_PORT}/health"
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(processing_service_url)
            
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "processing_service": "available",
                    "timestamp": response.json().get("timestamp")
                }
            else:
                return {
                    "status": "degraded",
                    "processing_service": "error",
                    "details": f"Processing service returned {response.status_code}"
                }
    except Exception as e:
        return {
            "status": "unhealthy",
            "processing_service": "unavailable",
            "error": str(e)
        } 