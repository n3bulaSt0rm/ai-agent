import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("processing_service")

async def start_processing_service():
    """Khởi động Processing Service"""
    logger.info("Starting Processing Service")
    
    # Import main function từ processing module
    from backend.services.processing.server import main
    
    # Chạy main function
    await main()

if __name__ == "__main__":
    try:
        asyncio.run(start_processing_service())
    except KeyboardInterrupt:
        logger.info("Processing service stopped by user")
    except Exception as e:
        logger.error(f"Error starting processing service: {e}")
        sys.exit(1) 