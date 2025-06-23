import sys
import os
import asyncio
import logging
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import processing service settings
from backend.common.config import settings

# Cấu hình logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("processing_service")

def start_processing_service():
    """Khởi động Processing Service bằng uvicorn"""
    logger.info(f"Starting Processing Service on port {settings.PROCESSING_PORT}")
    
    # Khởi động FastAPI app bằng uvicorn
    try:
        uvicorn.run(
            "backend.services.processing.server:app",
            host=settings.PROCESSING_HOST,
            port=settings.PROCESSING_PORT,
            reload=False
        )
    except Exception as e:
        logger.error(f"Error running uvicorn: {e}")
        raise

if __name__ == "__main__":
    try:
        start_processing_service()
    except KeyboardInterrupt:
        logger.info("Processing service stopped by user")
    except Exception as e:
        logger.error(f"Error starting processing service: {e}")
        sys.exit(1) 