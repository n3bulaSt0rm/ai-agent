from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os
import logging
import time
from datetime import datetime
import json

from backend.common.config import settings
from backend.services.web.api import auth, files, search, users
from backend.adapter.metadata import get_metadata_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("web_service")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="API for managing and querying school regulations PDF files",
    version="1.0.0",
    debug=True  # Enable debug mode
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add timing information to response headers"""
    start_time = time.time()
    
    # Log request information consistently for all requests
    logger.info(f"Request: {request.method} {request.url.path}?{request.url.query}")
    
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = str(int(process_time))
    
    # Log response status for all requests
    logger.info(f"Response: {response.status_code}")
    
    return response

# Include API routers
app.include_router(auth.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(users.router, prefix="/api")

# Static files and templates setup
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

# Create directories if they don't exist
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Setup templates
templates = Jinja2Templates(directory=templates_dir)

# Basic health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


# Webhook endpoint for status updates
@app.post("/api/webhook/status-update")
async def status_update_webhook(request: Request):
    """
    Webhook for receiving status updates from the processing service.
    Supports:
    - Updating file status
    - Adding processed page_range to pages_processed_range
    - Handling deleting and restoring transitions
    """
    try:
        data = await request.json()
        
        if not all(k in data for k in ["file_id", "status"]):
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        file_id = data.get("file_id")  # This is the UUID
        status = data.get("status")
        page_range = data.get("page_range")  # Optional field
        action = data.get("action")  # Optional field for delete/restore operations
        previous_status = data.get("previous_status")  # Optional field for restore
        
        # Log the webhook request
        if page_range:
            logger.info(f"Received webhook update for file {file_id}: status={status}, page_range={page_range}")
        else:
            logger.info(f"Received webhook update for file {file_id}: status={status}, action={action}")
        
        # Get the metadata DB
        db = get_metadata_db()
        
        # First, get the current file info to check page_range and current status
        file_info = db.get_pdf_file_by_uuid(file_id)
        if not file_info:
            logger.error(f"File {file_id} not found")
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")
        
        # Special handling for delete/restore actions
        if action == "delete" and status == "success" and file_info["status"] == "deleting":
            # Complete the delete action by changing status to deleted
            result = db.update_pdf_status_by_uuid(file_id, "deleted")
            if not result:
                logger.error(f"Failed to update status to deleted for file {file_id}")
                raise HTTPException(status_code=500, detail=f"Failed to update status to deleted for file {file_id}")
            logger.info(f"Successfully completed deletion for file {file_id}")
            return {"message": f"File {file_id} deletion completed successfully"}
            
        elif action == "restore" and status == "success" and file_info["status"] == "restoring":
            # Get previous status from webhook data or file info
            target_status = previous_status or file_info.get("previous_status") or "pending"
            
            # Complete the restore action by changing status to previous_status
            result = db.update_pdf_status_by_uuid(file_id, target_status)
            if not result:
                logger.error(f"Failed to update status to {target_status} for file {file_id}")
                raise HTTPException(status_code=500, detail=f"Failed to update status for file {file_id}")
            logger.info(f"Successfully completed restoration for file {file_id} to status {target_status}")
            return {"message": f"File {file_id} restoration completed successfully"}
        
        # If page_range is provided, update the pages_processed_range
        if page_range and status == "processed":
            # Get current processed ranges
            current_ranges = []
            if file_info.get("pages_processed_range"):
                try:
                    current_ranges = json.loads(file_info["pages_processed_range"])
                    if not isinstance(current_ranges, list):
                        current_ranges = []
                except:
                    current_ranges = []
            
            # Check if page_range already exists
            if page_range not in current_ranges:
                # Add the new page_range
                new_processed_ranges = current_ranges + [page_range]
                
                # Update pages_processed_range
                result = db.update_pdf_status_by_uuid(
                    file_id, 
                    file_info["status"],  # Keep current status
                    pages_processed_range=json.dumps(new_processed_ranges)
                )
                
                if not result:
                    logger.error(f"Failed to update pages_processed_range for file {file_id}")
                    raise HTTPException(status_code=500, detail=f"Failed to update pages_processed_range for file {file_id}")
                
                logger.info(f"Added page range {page_range} to file {file_id}, total ranges: {len(new_processed_ranges)}")
        
        # Always update status if it's different from current and not a special action
        if status != file_info["status"] and status not in ["success", "failed"]:
            # Update status in database by UUID
            result = db.update_pdf_status_by_uuid(file_id, status)
            
            if not result:
                logger.error(f"Failed to update status for file {file_id}")
                raise HTTPException(status_code=404, detail=f"File {file_id} not found")
                
            logger.info(f"Successfully updated file {file_id} status to {status}")
        
        return {"message": f"File {file_id} updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")

# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info(f"Starting {settings.APP_NAME}")
    
    # Initialize database
    get_metadata_db()
    
    logger.info("Web service started successfully")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info(f"Shutting down {settings.APP_NAME}")

# Run the application
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "web_server:app",
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        reload=settings.DEBUG
    ) 