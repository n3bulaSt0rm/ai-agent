"""
Mock Processing Service for handling document processing tasks.
This service listens for messages from the messaging service and simulates processing.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Dict, Any
import random
import httpx

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Import messaging after logging setup to capture its logs too
from backend.services.messaging import create_subscription, publish_message
from backend.core.config import settings

async def send_status_update(file_id: str, status: str):
    """
    Send status update to web service via webhook
    
    Args:
        file_id: UUID of the file
        status: Status value to set
    """
    webhook_url = settings.WEB_SERVICE_URL
    logger.info(f"Sending status update to webhook: {webhook_url} - file_id={file_id}, status={status}")
    
    data = {
        "file_id": file_id,
        "status": status
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=data)
            if response.status_code == 200:
                logger.info(f"Successfully sent status update: {response.text}")
            else:
                logger.error(f"Error sending status update: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Exception sending status update: {e}")

async def process_document(message_data: Dict[str, Any]):
    """
    Mock function to simulate document processing.
    In a real implementation, this would:
    1. Download the document from storage
    2. Extract text using OCR
    3. Create and store embeddings
    4. Update database with metadata
    
    Args:
        message_data: Message data containing document information
    """
    file_id = message_data.get("file_id")
    file_path = message_data.get("file_path")
    
    if not file_id or not file_path:
        logger.error("Missing file_id or file_path in message data")
        return
    
    logger.info(f"Started processing document: {file_id} at {file_path}")
    
    # Update status to processing
    await send_status_update(file_id, "processing")
    
    # Simulate processing stages with random delays
    processing_stages = [
        "Downloading document",
        "Extracting text with OCR",
        "Creating embeddings",
        "Storing vectors in database",
        "Updating metadata"
    ]
    
    total_stages = len(processing_stages)
    
    for i, stage in enumerate(processing_stages):
        # Simulate work
        delay = random.uniform(1.0, 3.0)
        await asyncio.sleep(delay)
        
        # Log progress
        progress = int((i + 1) / total_stages * 100)
        logger.info(f"Processing document {file_id}: {stage} - {progress}% complete")
    
    # Update status to processed when complete
    await send_status_update(file_id, "processed")
    logger.info(f"Completed processing document: {file_id}")

async def mark_document_deleted(message_data: Dict[str, Any]):
    """
    Mock function to simulate marking a document as deleted in Qdrant.
    In a real implementation, this would update the IsDeleted flag in Qdrant
    for all vectors associated with this file.
    
    Args:
        message_data: Message data containing deletion information
    """
    file_id = message_data.get("file_id")
    is_deleted = message_data.get("is_deleted", True)
    
    if not file_id:
        logger.error("Missing file_id in mark_deleted message")
        return
    
    logger.info(f"Marking document {file_id} as {'deleted' if is_deleted else 'not deleted'} in vector database")
    
    # Simulate work
    delay = random.uniform(0.5, 2.0)
    await asyncio.sleep(delay)
    
    # Update status based on deletion status
    if is_deleted:
        await send_status_update(file_id, "deleted")
    else:
        await send_status_update(file_id, "processed")
    
    logger.info(f"Successfully marked document {file_id} as {'deleted' if is_deleted else 'not deleted'} in vector database")

async def handle_processing_message(message_data: Dict[str, Any]):
    """
    Handler for incoming processing messages.
    
    Args:
        message_data: Message data containing processing instructions
    """
    logger.info(f"Received processing message: {message_data}")
    
    try:
        action = message_data.get("action", "")
        
        if action == "process" or action == "process_pdf":
            # Process the document asynchronously
            asyncio.create_task(process_document(message_data))
        elif action == "delete" or action == "mark_deleted":
            # Mark document as deleted in Qdrant
            message_data["is_deleted"] = True
            asyncio.create_task(mark_document_deleted(message_data))
        elif action == "restore":
            # Mark document as not deleted in Qdrant
            message_data["is_deleted"] = False
            asyncio.create_task(mark_document_deleted(message_data))
        else:
            logger.warning(f"Unknown action in message: {action}")
    except Exception as e:
        logger.error(f"Error processing message: {e}")

async def main():
    """Main entry point for the processing service."""
    logger.info("Starting processing service...")
    
    # Create subscription to the processing topic
    await create_subscription(
        settings.PDF_PROCESSING_TOPIC,
        "pdf-processing-subscription",
        handle_processing_message
    )
    
    logger.info(f"Listening for messages on topic: {settings.PDF_PROCESSING_TOPIC}")
    
    # Keep the service running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main()) 