"""
Processing Service for document processing tasks.
This service listens for messages from the messaging service and processes documents.
"""

# Standard library imports
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Third-party imports
import httpx

# Configure logging before other imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Local imports
from backend.services.messaging import create_subscription, publish_message
from backend.core.config import settings
from backend.services.processing.rag.handler import start_monitoring_async
from backend.services.processing.rag.extractors.azure.main import process_document as azure_process_document
from backend.services.processing.rag.extractors.azure.summary_table import process_file
from backend.services.processing.rag.chunkers.markdown_chunker import MarkdownChunker
from backend.services.processing.rag.chunkers.sematic_chunker import ProtonxSemanticChunker
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.services.processing.rag.common.qdrant import ChunkData

# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

# Configuration
SEMANTIC_CHUNKER_THRESHOLD = 0.3
SEMANTIC_CHUNKER_MODEL = "bkai-foundation-models/vietnamese-bi-encoder"
QDRANT_BATCH_SIZE = 8


async def send_status_update(file_id: str, status: str) -> bool:
    """
    Send status update to web service via webhook.
    
    Args:
        file_id: UUID of the file
        status: Status value to set
    
    Returns:
        bool: True if status update was successful, False otherwise
    """
    webhook_url = settings.WEB_SERVICE_URL
    logger.info(f"Sending status update: file_id={file_id}, status={status}")
    
    data = {"file_id": file_id, "status": status}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=data)
            if response.status_code == 200:
                logger.info(f"Status update successful: {response.text}")
                return True
            else:
                logger.error(f"Status update failed: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Exception during status update: {e}")
        return False


async def extract_text(file_path: str, page_range: Optional[str] = None) -> str:
    """
    Extract text from document using Azure Document Intelligence.
    
    Args:
        file_path: Path or URL to the document
        page_range: Optional range of pages to process (e.g., "1-3")
        
    Returns:
        str: Extracted markdown content
        
    Raises:
        ValueError: If text extraction fails
    """
    logger.info(f"Extracting text from document: {file_path}")
    markdown_content = azure_process_document(file_path, page_range)
    
    if not markdown_content:
        raise ValueError("Failed to extract text from document")
    
    return markdown_content


async def process_tables(markdown_content: str) -> str:
    """
    Process tables in markdown content and convert them to descriptive text.
    
    Args:
        markdown_content: Markdown content containing tables
        
    Returns:
        str: Processed content with tables converted to text
    """
    logger.info("Converting tables to descriptive text")
    processed_content = process_file(markdown_content)
    
    return processed_content if processed_content else markdown_content


async def create_markdown_chunks(markdown_content: str) -> List[Dict[str, Any]]:
    """
    Chunk markdown content by headers.
    
    Args:
        markdown_content: Markdown content to chunk
        
    Returns:
        List[Dict[str, Any]]: List of markdown chunks
    """
    logger.info("Chunking text by markdown headers")
    md_chunker = MarkdownChunker()
    markdown_chunks = md_chunker.chunk_text(markdown_content)
    logger.info(f"Created {len(markdown_chunks)} markdown chunks")
    
    return markdown_chunks


async def create_semantic_chunks(
    markdown_chunks: List[Dict[str, Any]],
    file_id: str
) -> List[Dict[str, Any]]:
    """
    Create semantic chunks from markdown chunks.
    
    Args:
        markdown_chunks: List of markdown chunks
        file_id: ID of the file
        
    Returns:
        List[Dict[str, Any]]: List of semantic chunks
    """
    logger.info("Creating semantic chunks")
    semantic_chunker = ProtonxSemanticChunker(
        threshold=SEMANTIC_CHUNKER_THRESHOLD,
        model=SEMANTIC_CHUNKER_MODEL
    )
    
    semantic_chunks = semantic_chunker.process_chunks(markdown_chunks, file_id)
    logger.info(f"Created {len(semantic_chunks)} semantic chunks")
    
    return semantic_chunks


def create_chunk_objects(
    semantic_chunks: List[Dict[str, Any]],
    file_id: str
) -> List[ChunkData]:
    """
    Convert semantic chunks to ChunkData objects.
    
    Args:
        semantic_chunks: List of semantic chunks
        file_id: ID of the file
        
    Returns:
        List[ChunkData]: List of ChunkData objects
    """
    chunk_objects = []
    
    for chunk in semantic_chunks:
        # Extract parent_chunk_id from metadata if present
        parent_chunk_id = 0
        if "metadata" in chunk and "parent_chunk_id" in chunk["metadata"]:
            parent_chunk_id = chunk["metadata"]["parent_chunk_id"]
        
        chunk_obj = ChunkData(
            chunk_id=chunk["chunk_id"],
            content=chunk["content"],
            file_id=file_id,
            parent_chunk_id=parent_chunk_id
        )
        
        chunk_objects.append(chunk_obj)
    
    return chunk_objects


async def embed_and_store_chunks(
    chunk_objects: List[ChunkData],
    file_id: str,
    file_created_at: Optional[str] = None,
    keywords: Optional[List[str]] = None
) -> int:
    """
    Embed chunks and store them in Qdrant.
    
    Args:
        chunk_objects: List of ChunkData objects
        file_id: ID of the file
        file_created_at: When the file was created
        keywords: List of keywords to associate with the chunks
        
    Returns:
        int: Number of chunks stored
    """
    logger.info("Embedding chunks and storing in Qdrant")
    
    # Initialize the embedding module
    embedding_module = VietnameseEmbeddingModule(
        qdrant_host=settings.QDRANT_HOST,
        qdrant_port=settings.QDRANT_PORT,
        collection_name=settings.QDRANT_COLLECTION
    )
    
    # Add metadata for Qdrant storage
    metadata = {
        "file_id": file_id,
        "is_deleted": False
    }
    
    # Add file_created_at if provided
    if file_created_at:
        metadata["file_created_at"] = file_created_at
        
    # Add keywords if provided
    if keywords:
        metadata["keywords"] = keywords
    
    # Generate embeddings for all chunk objects
    chunk_texts = [chunk.content for chunk in chunk_objects]
    embeddings = embedding_module.generate_embeddings_batch(chunk_texts)
    
    # Add metadata to chunks
    for chunk in chunk_objects:
        for key, value in metadata.items():
            setattr(chunk, key, value)
    
    # Store embeddings directly in Qdrant
    embedding_module.qdrant_manager.store_embeddings(
        chunk_objects, 
        embeddings, 
        batch_size=QDRANT_BATCH_SIZE
    )
    
    logger.info(f"Stored {len(chunk_objects)} embeddings in Qdrant")
    return len(chunk_objects)


async def process_document(message_data: Dict[str, Any]) -> None:
    """
    Process a document through the entire RAG pipeline:
    1. Extract text using Azure Document Intelligence
    2. Convert tables to text descriptions
    3. Chunk the text by markdown headers
    4. Further divide into semantic chunks
    5. Embed chunks and store in Qdrant
    
    Args:
        message_data: Message data containing document information
    """
    file_id = message_data.get("file_id")
    file_path = message_data.get("file_path")
    page_range = message_data.get("page_range")
    file_created_at = message_data.get("file_created_at")
    keywords = message_data.get("keywords", [])
    
    if not file_id or not file_path:
        logger.error("Missing file_id or file_path in message data")
        return
    
    logger.info(f"Started processing document: {file_id} at {file_path}")
    
    # Update status to processing
    await send_status_update(file_id, "processing")
    
    try:
        # Generate a processing ID for tracing
        processing_id = str(uuid.uuid4())
        logger.info(f"Processing ID: {processing_id}")
        
        # Step 1: Extract text from document
        markdown_content = await extract_text(file_path, page_range)
        
        # Step 2: Process tables
        markdown_content = await process_tables(markdown_content)
        
        # Step 3: Chunk markdown
        markdown_chunks = await create_markdown_chunks(markdown_content)
        
        # Step 4: Create semantic chunks
        semantic_chunks = await create_semantic_chunks(markdown_chunks, file_id)
        
        # Step 5: Create chunk objects
        chunk_objects = create_chunk_objects(semantic_chunks, file_id)
        
        # Step 6: Embed and store chunks
        await embed_and_store_chunks(chunk_objects, file_id, file_created_at, keywords)
        
        # Update status to processed
        await send_status_update(file_id, "processed")
        logger.info(f"Completed processing document: {file_id}")
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        # Update status to error
        await send_status_update(file_id, "error")


async def mark_document_deleted(message_data: Dict[str, Any]) -> None:
    """
    Mark a document as deleted in Qdrant.
    Updates the is_deleted flag in Qdrant for all vectors associated with the file.
    
    Args:
        message_data: Message data containing deletion information
    """
    file_id = message_data.get("file_id")
    is_deleted = message_data.get("is_deleted", True)
    
    if not file_id:
        logger.error("Missing file_id in mark_deleted message")
        return
    
    logger.info(f"Marking document {file_id} as {'deleted' if is_deleted else 'not deleted'}")
    
    try:
        # Initialize the embedding module to access Qdrant
        embedding_module = VietnameseEmbeddingModule(
            qdrant_host=settings.QDRANT_HOST,
            qdrant_port=settings.QDRANT_PORT,
            collection_name=settings.QDRANT_COLLECTION
        )
        
        # Update is_deleted flag for all vectors with this file_id
        qdrant_manager = embedding_module.qdrant_manager
        qdrant_manager.update_is_deleted_flag(file_id, is_deleted)
        
        # Update status based on deletion status
        new_status = "deleted" if is_deleted else "processed"
        await send_status_update(file_id, new_status)
        
        logger.info(f"Successfully marked document {file_id} as {new_status}")
    
    except Exception as e:
        logger.error(f"Error marking document as deleted: {str(e)}", exc_info=True)
        await send_status_update(file_id, "error")


async def handle_processing_message(message_data: Dict[str, Any]) -> None:
    """
    Handler for incoming processing messages.
    
    Args:
        message_data: Message data containing processing instructions
    """
    logger.info(f"Received processing message: {message_data}")
    
    try:
        action = message_data.get("action", "")
        
        # Map actions to handlers
        action_handlers = {
            "process": process_document,
            "process_pdf": process_document,
            "delete": lambda data: mark_document_deleted({**data, "is_deleted": True}),
            "mark_deleted": lambda data: mark_document_deleted({**data, "is_deleted": True}),
            "restore": lambda data: mark_document_deleted({**data, "is_deleted": False}),
            "update_keywords": process_document
        }
        
        # Get the handler for this action
        handler = action_handlers.get(action)
        
        if handler:
            # Create task to handle the message asynchronously
            asyncio.create_task(handler(message_data))
        else:
            logger.warning(f"Unknown action in message: {action}")
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


async def main() -> None:
    """Main entry point for the processing service."""
    logger.info("Starting processing service...")
    
    try:
        # Create subscription to the processing topic
        await create_subscription(
            settings.PDF_PROCESSING_TOPIC,
            "pdf-processing-subscription",
            handle_processing_message
        )
        
        logger.info(f"Listening for messages on topic: {settings.PDF_PROCESSING_TOPIC}")
        
        # Start the Gmail monitoring service
        try:
            logger.info("Starting Gmail monitoring service...")
            gmail_task = await start_monitoring_async()
            logger.info("Gmail monitoring service started successfully")
        except Exception as e:
            logger.error(f"Failed to start Gmail monitoring service: {e}", exc_info=True)
            # Continue with the processing service even if Gmail monitoring fails
        
        # Keep the service running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down processing service...")
    except Exception as e:
        logger.error(f"Error in main service loop: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main()) 