from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os
import logging
import time
from datetime import datetime

from backend.core.config import settings
from backend.services.web.api import auth, files, query
from backend.db.metadata import get_metadata_db

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
    
    # Print request information for debugging
    print(f"Request: {request.method} {request.url.path}?{request.url.query}")
    
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = str(int(process_time))
    
    # Print response status for debugging
    print(f"Response: {response.status_code}")
    
    return response

# Include API routers
app.include_router(auth.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(query.router, prefix="/api")

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

# Root endpoint redirects to admin UI
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the admin UI"""
    # In a real implementation, we would create a proper index.html template
    # For now, redirect to the admin UI
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="0;url=/admin">
        <title>Redirecting...</title>
    </head>
    <body>
        <p>Redirecting to admin interface...</p>
    </body>
    </html>
    """

# Admin UI endpoint
@app.get("/admin", response_class=HTMLResponse)
async def admin_ui(request: Request):
    """Serve the admin UI"""
    # In a real implementation, this would be a proper SPA
    # For now, just return a placeholder
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Agent Admin</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding-top: 20px; }
            .loading { display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AI Agent Admin Interface</h1>
            <p>This is a placeholder for the React-based admin UI.</p>
            <p>For now, you can use the API directly:</p>
            <ul>
                <li><a href="/docs" target="_blank">API Documentation</a></li>
            </ul>
        </div>
        <script>
            // In a real implementation, this would load the React app
            console.log("Admin UI loaded");
        </script>
    </body>
    </html>
    """

# Webhook endpoint for status updates
@app.post("/api/webhook/status-update")
async def status_update_webhook(request: Request):
    """
    Webhook for receiving status updates from the processing service.
    Simplified to only use file_id (UUID) and status.
    """
    try:
        data = await request.json()
        
        if not all(k in data for k in ["file_id", "status"]):
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        file_id = data.get("file_id")  # This is the UUID
        status = data.get("status")
        
        # Log the webhook request
        logger.info(f"Received webhook update for file {file_id}: status={status}")
        
        # Get the metadata DB
        db = get_metadata_db()
        
        # Update status in database by UUID
        result = db.update_pdf_status_by_uuid(file_id, status)
        
        if not result:
            logger.error(f"Failed to update status for file {file_id}")
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")
            
        logger.info(f"Successfully updated file {file_id} status to {status}")
        return {"message": f"File {file_id} status updated to {status}"}
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