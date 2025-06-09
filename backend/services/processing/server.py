"""
Processing Service for document processing tasks.
This service listens for messages from the messaging service and processes documents.
"""

# Standard library imports
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Literal
from datetime import datetime

# Third-party imports
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configure logging once at the very beginning
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Local imports
from backend.core.config import settings
from backend.services.messaging import create_subscription, publish_message
from backend.services.processing.rag.handler import start_gmail_monitoring
from backend.services.processing.rag.extractors.azure.main import process_document as azure_process_document
from backend.services.processing.rag.extractors.azure.summary_table import process_file
from backend.services.processing.rag.chunkers.markdown_chunker import MarkdownChunker
from backend.services.processing.rag.chunkers.chunker_adapter import UniversalChunkerAdapter
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.services.processing.rag.common.qdrant import ChunkData
from backend.services.processing.rag.common.cuda import CudaMemoryManager

# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database path
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "admin.db"

# Get configuration from settings
PROCESSING_PORT = settings.PROCESSING_PORT
PROCESSING_HOST = settings.PROCESSING_HOST
DENSE_MODEL_NAME = settings.DENSE_MODEL_NAME
SPARSE_MODEL_NAME = settings.SPARSE_MODEL_NAME
RERANKER_MODEL_NAME = settings.RERANKER_MODEL_NAME
QDRANT_BATCH_SIZE = settings.QDRANT_BATCH_SIZE
VECTOR_SIZE = settings.VECTOR_SIZE

# Chunker configuration from settings
CHUNKER_TYPE = settings.CHUNKER_TYPE
RECURSIVE_CHUNKER_SIZE = settings.RECURSIVE_CHUNKER_SIZE
RECURSIVE_CHUNKER_OVERLAP = settings.RECURSIVE_CHUNKER_OVERLAP
RECURSIVE_CHUNKER_MIN_LENGTH = settings.RECURSIVE_CHUNKER_MIN_LENGTH
RECURSIVE_CHUNKER_MAX_SEQ_LENGTH = settings.RECURSIVE_CHUNKER_MAX_SEQ_LENGTH

# Module singletons - will be initialized during startup
class ModuleSingletons:
    universal_chunker = None
    embedding_module = None
    cuda_memory_manager = None

# Create the singletons instance that will be used throughout the application
modules = ModuleSingletons()

# Create FastAPI app
app = FastAPI(
    title="Document Processing Service",
    description="Service for processing PDF documents and extracting semantic information",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint with detailed response
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "online",
        "message": "Service is running normally",
        "timestamp": datetime.now().isoformat()
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Processing Service Running"}


def update_file_status(file_id: str, status: str, page_range: str = None) -> bool:
    """
    Update file status directly in the SQLite database.
    
    Args:
        file_id: UUID of the file
        status: New status to set
        page_range: Optional page range being processed (for "processed" status)
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        logger.info(f"Updating file status: file_id={file_id}, status={status}" + 
                   (f", page_range={page_range}" if page_range else ""))
        
        with sqlite3.connect(str(DB_PATH)) as db_conn:
            # Check if file exists and get current data
            query_result = db_conn.execute("SELECT status, pages_processed_range FROM files_management WHERE uuid = ?", (file_id,))
            result = query_result.fetchone()
            
            if not result:
                logger.warning(f"No file found with UUID {file_id}")
                return False
            
            # Handle pages_processed_range when page_range is provided
            if page_range:
                current_ranges = []
                if result[1]:  # pages_processed_range exists
                    try:
                        current_ranges = json.loads(result[1])
                        if not isinstance(current_ranges, list):
                            current_ranges = []
                    except (json.JSONDecodeError, TypeError, ValueError):
                        current_ranges = []
                
                # Add new page_range if not already present
                if page_range not in current_ranges:
                    current_ranges.append(page_range)
                
                # Update both status and pages_processed_range
                db_conn.execute(
                    "UPDATE files_management SET status = ?, pages_processed_range = ?, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
                    (status, json.dumps(current_ranges), file_id)
                )
                logger.info(f"Updated file {file_id} status to {status} and added page range {page_range}, total ranges: {len(current_ranges)}")
            else:
                # Standard status update without page range handling
                db_conn.execute(
                    "UPDATE files_management SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
                    (status, file_id)
                )
                logger.info(f"Updated file {file_id} status to {status}")
            
            db_conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Error updating file status: {e}")
        return False

def extract_text(file_path: str, page_range: Optional[str] = None) -> str:
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


def process_tables(markdown_content: str) -> str:
    """
    Process tables in markdown content and convert them to descriptive text.
    
    Args:
        markdown_content: Markdown content containing tables
        
    Returns:
        str: Processed content with tables converted to text
    """
    logger.info("Converting tables to descriptive text")
    processed_content = process_file(markdown_content)
    return processed_content if processed_content is not None else markdown_content


def create_markdown_chunks(markdown_content: str) -> List[Dict[str, Any]]:
    """
    Chunk markdown content by headers.
    
    Args:
        markdown_content: Markdown content to chunk
        
    Returns:
        List[Dict[str, Any]]: List of markdown chunks
    """
    if not markdown_content or not markdown_content.strip():
        logger.warning("Empty markdown content provided")
        return []
    
    logger.info("Chunking text by markdown headers")
    md_chunker = MarkdownChunker()
    markdown_chunks = md_chunker.chunk_text(markdown_content)
    
    if not markdown_chunks:
        logger.warning("No chunks created from markdown content")
        markdown_chunks = []
    
    logger.info(f"Created {len(markdown_chunks)} markdown chunks")
    return markdown_chunks


def process_markdown_chunks(
    markdown_chunks: List[Dict[str, Any]],
    file_id: str
) -> List[Dict[str, Any]]:
    """
    Process markdown chunks using the configured chunker.
    
    Args:
        markdown_chunks: List of markdown chunks
        file_id: ID of the file
        
    Returns:
        List[Dict[str, Any]]: List of processed chunks
    """
    logger.info(f"Processing chunks using {CHUNKER_TYPE} chunker")
    
    chunks = modules.universal_chunker.process_chunks(markdown_chunks, file_id)
    
    logger.info(f"Created {len(chunks)} chunks using {CHUNKER_TYPE} chunker")
    
    return chunks


def create_chunk_objects(
    chunks: List[Dict[str, Any]],
    file_id: str,
    file_created_at: Optional[str] = None
) -> List[ChunkData]:
    """
    Convert chunks to ChunkData objects.
    
    Args:
        chunks: List of chunks
        file_id: ID of the file
        file_created_at: File creation timestamp
        
    Returns:
        List[ChunkData]: List of ChunkData objects
    """
    if not chunks:
        logger.warning("No chunks provided for chunk object creation")
        return []
    
    chunk_objects = []
    
    for chunk in chunks:
        # Extract parent_chunk_id from metadata if present
        parent_chunk_id = 0
        if "metadata" in chunk and "parent_chunk_id" in chunk["metadata"]:
            parent_chunk_id = chunk["metadata"]["parent_chunk_id"]
        
        chunk_obj = ChunkData(
            chunk_id=chunk["chunk_id"],
            content=chunk["content"],
            file_id=file_id,
            parent_chunk_id=parent_chunk_id,
            file_created_at=file_created_at
        )
        
        chunk_objects.append(chunk_obj)
    
    return chunk_objects


def embed_and_store_chunks(
    chunk_objects: List[ChunkData],
    file_id: str,
) -> int:
    
    if not chunk_objects:
        logger.warning("No chunk objects to embed and store")
        return 0
    
    
    modules.embedding_module.index_documents(chunk_objects, batch_size=QDRANT_BATCH_SIZE)
    
    return len(chunk_objects)

async def process_document(message_data: Dict[str, Any]) -> None:
    file_id = message_data.get("file_id")
    file_path = message_data.get("file_path")
    page_range = message_data.get("page_range")
    file_created_at = message_data.get("file_created_at")

    if not file_id or not file_path:
        logger.error("Missing file_id or file_path in message data")
        return
    
    logger.info(f"Started processing document: {file_id} at {file_path}")
    
    # Set status to processing and track page range
    update_file_status(file_id, "processing", page_range)

    try:
        # Step 1: Extract text from document
        markdown_content = extract_text(file_path, page_range)
        
        # Step 2: Process tables
        markdown_content = process_tables(markdown_content)
        
        # Step 3: Chunk markdown
        markdown_chunks = create_markdown_chunks(markdown_content)
        
        # Step 4: Create chunks from markdown chunks
        processed_chunks = process_markdown_chunks(markdown_chunks, file_id)
        
        # Step 5: Create chunk objects
        chunk_objects = create_chunk_objects(processed_chunks, file_id, file_created_at)
        
        # Step 6: Embed and store chunks
        stored_count = embed_and_store_chunks(chunk_objects, file_id)
        logger.info(f"Successfully stored {stored_count} chunks for document {file_id}")
        
        # Update status to processed
        update_file_status(file_id, "processed")
        logger.info(f"Completed processing document: {file_id}")
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        update_file_status(file_id, "error")

async def handle_document_deletion_status(message_data: Dict[str, Any]) -> None:
    """
    Handle document deletion/restoration operations.
    Updates the is_deleted flag in Qdrant and manages status in database.
    
    Args:
        message_data: Message data containing file_id and action (delete/restore)
    """
    file_id = message_data.get("file_id")
    action = message_data.get("action")
    
    if not file_id:
        logger.error("Missing file_id in deletion message")
        return
        
    if action not in ["delete", "restore"]:
        logger.error(f"Invalid action: {action}. Must be 'delete' or 'restore'")
        return
    
    logger.info(f"Processing {action} action for document {file_id}")
    
    try:
        qdrant_manager = modules.embedding_module.qdrant_manager
        
        if action == "delete":
            # Update is_deleted flag to True in Qdrant
            result = qdrant_manager.update_is_deleted_flag(file_id, True)
            
            if result:
                # Get current status to save as previous_status
                with sqlite3.connect(str(DB_PATH)) as db_conn:
                    status_query = db_conn.execute("SELECT status FROM files_management WHERE uuid = ?", (file_id,))
                    current_status = status_query.fetchone()
                    
                    if current_status:
                        # Save current status as previous_status and set status to 'deleted'
                        db_conn.execute(
                            "UPDATE files_management SET status = ?, previous_status = ?, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
                            ("deleted", current_status[0], file_id)
                        )
                        db_conn.commit()
                        logger.info(f"Document {file_id} marked as deleted, previous status saved: {current_status[0]}")
                    else:
                        logger.warning(f"File {file_id} not found in database")
            else:
                logger.error(f"Failed to update is_deleted flag in Qdrant for file {file_id}")
                
        elif action == "restore":
            # Update is_deleted flag to False in Qdrant
            result = qdrant_manager.update_is_deleted_flag(file_id, False)
            
            if result:
                # Restore status from previous_status
                with sqlite3.connect(str(DB_PATH)) as db_conn:
                    prev_status_query = db_conn.execute("SELECT previous_status FROM files_management WHERE uuid = ?", (file_id,))
                    previous_status_result = prev_status_query.fetchone()
                    
                    if previous_status_result and previous_status_result[0]:
                        restore_status = previous_status_result[0]
                        db_conn.execute(
                            "UPDATE files_management SET status = ?, previous_status = NULL, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
                            (restore_status, file_id)
                        )
                        db_conn.commit()
                        logger.info(f"Document {file_id} restored to status: {restore_status}")
                    else:
                        # Fallback to 'pending' if no previous status
                        update_file_status(file_id, "pending")
                        logger.info(f"Document {file_id} restored to default status: pending")
            else:
                logger.error(f"Failed to update is_deleted flag in Qdrant for file {file_id}")
                
    except Exception as e:
        logger.error(f"Error processing {action} for document {file_id}: {e}")
        update_file_status(file_id, "error")

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
            "delete": handle_document_deletion_status,
            "restore": handle_document_deletion_status,
        }
        
        # Get the handler for this action
        handler = action_handlers.get(action)
        
        if handler:
            await handler(message_data)
        else:
            logger.error(f"Unsupported action: {action}")
    
    except Exception as e:
        file_id = message_data.get("file_id", "unknown")
        logger.error(f"Error processing message: {e}")
        
        # Try to update error status if we have a file_id
        if file_id != "unknown":
            update_file_status(file_id, "error")

def initialize_modules():
    """Initialize all required modules"""
    try:
        # Verify database exists
        logger.info("Verifying database exists")
        if not DB_PATH.exists():
            logger.error(f"Database file not found at {DB_PATH}")
            return False
        logger.info("Database file verified")
        
        # Initialize CUDA memory manager
        logger.info("Initializing CUDA Memory Manager")
        modules.cuda_memory_manager = CudaMemoryManager()
        logger.info("CUDA Memory Manager initialized successfully")
        
        # Initialize the universal chunker
        logger.info(f"Initializing universal chunker with type: {CHUNKER_TYPE}")
        modules.universal_chunker = UniversalChunkerAdapter(
            chunker_type=CHUNKER_TYPE,
            model=DENSE_MODEL_NAME,
            chunk_size=RECURSIVE_CHUNKER_SIZE,
            chunk_overlap=RECURSIVE_CHUNKER_OVERLAP,
            min_chunk_length=RECURSIVE_CHUNKER_MIN_LENGTH,
            max_sequence_length=RECURSIVE_CHUNKER_MAX_SEQ_LENGTH
        )
        logger.info(f"Universal Chunker initialized successfully")
        
        # Initialize the embedding module with hybrid search capabilities
        logger.info("Initializing Vietnamese Embedding Module")
        modules.embedding_module = VietnameseEmbeddingModule(
            qdrant_host=settings.QDRANT_HOST,
            qdrant_port=settings.QDRANT_PORT,
            collection_name=settings.QDRANT_COLLECTION_NAME,
            dense_model_name=settings.DENSE_MODEL_NAME,
            sparse_model_name=settings.SPARSE_MODEL_NAME,
            reranker_model_name=settings.RERANKER_MODEL_NAME,
            vector_size=VECTOR_SIZE,
            memory_manager=modules.cuda_memory_manager  # Pass shared memory manager
        )
        logger.info("Vietnamese Embedding Module initialized successfully")
        
        return True
    except Exception as e:
        logger.error(f"Failed to initialize modules: {e}")
        return False

async def startup():
    """Startup event for the FastAPI application"""
    logger.info("Starting processing service...")
    
    # Initialize all required modules first
    if not initialize_modules():
        logger.error("Failed to initialize required modules. Service cannot start properly!")
        raise RuntimeError("Failed to initialize required modules. Service cannot start.")
    
    try:
        # Create subscription to the processing topic
        logger.info("Creating subscription to processing topic...")
        await create_subscription(
            settings.PDF_PROCESSING_TOPIC,
            "processing_service_subscription",
            handle_processing_message
        )
        logger.info("Processing subscription created successfully")
        
        # Start the Gmail monitoring service
        logger.info("Starting Gmail monitoring service...")
        asyncio.create_task(start_gmail_monitoring())
        logger.info("Gmail monitoring service started successfully")
        
        logger.info("All startup tasks completed successfully")
        
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to complete startup: {str(e)}")

# Register startup event
@app.on_event("startup")
async def on_startup():
    """FastAPI startup event handler"""
    try:
        await startup()
    except Exception as e:
        logger.critical(f"Failed to start service: {e}", exc_info=True)
        # In a real production environment, you might want to exit here
        raise

# Register shutdown event
@app.on_event("shutdown")
async def on_shutdown():
    """FastAPI shutdown event handler"""
    logger.info("Shutting down processing service...")
    
    # Cleanup modules
    if modules.embedding_module:
        logger.info("Cleaning up embedding module...")
        modules.embedding_module.cleanup()
        
    if modules.cuda_memory_manager:
        logger.info("Cleaning up CUDA memory...")
        modules.cuda_memory_manager.cleanup_memory(force=True)
        
    logger.info("Processing service shutdown complete")