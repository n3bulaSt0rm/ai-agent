import sys
import os
import logging

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import uvicorn
from backend.core.config import settings

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("web_service")

def start_web_service():
    """Khởi động Web Service"""
    logger.info(f"Starting Web Service on {settings.WEB_HOST}:{settings.WEB_PORT}")
    
    from backend.services.web.server import app
    
    # Khởi động uvicorn server
    uvicorn.run(
        app,
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        reload=settings.DEBUG
    )

if __name__ == "__main__":
    try:
        start_web_service()
    except KeyboardInterrupt:
        logger.info("Web service stopped by user")
    except Exception as e:
        logger.error(f"Error starting web service: {e}")
        sys.exit(1) 