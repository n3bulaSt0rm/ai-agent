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
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging once at the very beginning - only if not already configured
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
logger = logging.getLogger(__name__)

# Local imports
from backend.common.config import settings
from backend.adapter.message_queue.rabbitmq import get_rabbitmq_client
from backend.services.processing.rag.handler import start_gmail_monitoring, GmailHandler

from backend.services.processing.rag.extractors.azure.main import process_document as azure_process_document
from backend.services.processing.rag.extractors.azure.summary_table import process_file
from backend.services.processing.rag.chunkers.markdown_chunker import MarkdownChunker
from backend.services.processing.rag.chunkers.chunker_adapter import UniversalChunkerAdapter
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.services.processing.rag.common.qdrant import ChunkData
from backend.services.processing.rag.common.cuda import CudaMemoryManager
from backend.services.processing.rag.extractors.gemini.text_processor import process_text_document_from_url as gemini_process_text_from_url

# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

# Create log directory for chunk objects
LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "chunk_objects"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "admin.db"

# Status constants
class FileStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"
    DELETED = "deleted"

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
    gmail_handler = None

# Create the singletons instance that will be used throughout the application
modules = ModuleSingletons()

class TextProcessRequest(BaseModel):
    text: str

app = FastAPI(
    title="Document Processing Service",
    description="Service for processing PDF documents and extracting semantic information",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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

@app.post("/process-text")
async def process_text_endpoint(request: TextProcessRequest):
    """
    Process text content and return comprehensive information with sources
    
    Args:
        request: TextProcessRequest containing the text to process
        
    Returns:
        JSON response with the processed result
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")
        
        if modules.gmail_handler is None:
            logger.error("Gmail handler not initialized")
            raise HTTPException(status_code=500, detail="Text processing service not available - query module initialization failed")
        
        if not hasattr(modules.gmail_handler, 'query_module') or modules.gmail_handler.query_module is None:
            logger.error("Query module not initialized in Gmail handler")
            raise HTTPException(status_code=500, detail="Query module not available")
        
        logger.info(f"Processing text request with {len(request.text)} characters")
        
        # Process the text using the Gmail handler's Vietnamese Query Module
        response = await modules.gmail_handler.process_text_with_vietnamese_query_module(request.text)
        
        if not response:
            raise HTTPException(status_code=500, detail="Failed to process text")
        
        return {
            "status": "success",
            "response": response,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing text: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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
    Extract text from PDF document using Azure Document Intelligence.
    
    Args:
        file_path: Path or URL to the document
        page_range: Optional range of pages to process (e.g., "1-3")
        
    Returns:
        str: Extracted markdown content
        
    Raises:
        ValueError: If text extraction fails
    """
    logger.info(f"Extracting text from PDF document: {file_path}")
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
    file_created_at: Optional[str] = None,
    source: Optional[str] = None
) -> List[ChunkData]:
    """
    Convert chunks to ChunkData objects.
    
    Args:
        chunks: List of chunks
        file_id: ID of the file
        file_created_at: File creation timestamp
        source: Source file path
        
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
            file_created_at=file_created_at,
            source=source
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

def save_chunk_objects_to_log(chunk_objects: List[ChunkData], file_id: str, document_type: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filepath = LOG_DIR / f"{document_type}_{file_id}_{timestamp}.json"
        
        # Count tokens using model's tokenizer
        model = modules.embedding_module.dense_model
        chunks = []
        total_tokens = 0
        
        for chunk in chunk_objects:
            # Count tokens directly
            tokens = model.tokenizer.tokenize(chunk.content)
            token_count = len(tokens)
            total_tokens += token_count
            
            # Add chunk with token count
            chunks.append({
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "token_count": token_count
            })
        
        # Log token statistics
        avg_tokens = total_tokens / len(chunks) if chunks else 0
        logger.info(f"Token stats: Total={total_tokens}, Avg={avg_tokens:.1f}")
        
        # Save to file
        with open(log_filepath, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(chunks)} chunks to log")
        
    except Exception as e:
        logger.error(f"Error saving chunk log: {e}")
        # Fallback to basic logging without token counts
        try:
            simple_chunks = [{"chunk_id": chunk.chunk_id, "content": chunk.content} for chunk in chunk_objects]
            with open(log_filepath, 'w', encoding='utf-8') as f:
                json.dump(simple_chunks, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(simple_chunks)} chunks to log (without token counts)")
        except Exception as inner_e:
            logger.error(f"Failed to save even basic log: {inner_e}")

async def process_pdf_document(message_data: Dict[str, Any]) -> None:
    """Process PDF documents using Azure Document Intelligence"""
    file_id = message_data.get("file_id")
    file_path = message_data.get("file_path")
    page_range = message_data.get("page_range")
    file_created_at = message_data.get("file_created_at")

    logger.info(f"Started processing PDF document: {file_id} at {file_path}")
    
    update_file_status(file_id, FileStatus.PROCESSING, page_range)

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
        chunk_objects = create_chunk_objects(processed_chunks, file_id, file_created_at, file_path)
        
        # Step 6: Embed and store chunks
        stored_count = embed_and_store_chunks(chunk_objects, file_id)
        logger.info(f"Successfully stored {stored_count} chunks for PDF document {file_id}")
        
        # Save chunk objects to log
        save_chunk_objects_to_log(chunk_objects, file_id, "pdf")
        
        update_file_status(file_id, FileStatus.PROCESSED)
        logger.info(f"Completed processing PDF document: {file_id}")
        
    except Exception as e:
        logger.error(f"Error processing PDF document: {str(e)}", exc_info=True)
        update_file_status(file_id, FileStatus.ERROR)

async def process_txt_document(message_data: Dict[str, Any]) -> None:
    """Process text documents using Gemini for chunking"""
    file_id = message_data.get("file_id")
    file_path = message_data.get("file_path")
    file_created_at = message_data.get("file_created_at")
    source = message_data.get("source")

    logger.info(f"Started processing text document: {file_id} at {file_path}")
    
    update_file_status(file_id, FileStatus.PROCESSING)

    try:
        logger.info("Processing text file via Gemini File API")
        gemini_chunks = gemini_process_text_from_url(file_path, file_id)
        
        # Validation for gemini_chunks
        if not gemini_chunks:
            logger.error(f"No chunks returned from Gemini processing for file {file_id}")
            update_file_status(file_id, FileStatus.ERROR)
            return
            
        if not isinstance(gemini_chunks, list):
            logger.error(f"Invalid chunk format returned from Gemini for file {file_id}: expected list, got {type(gemini_chunks)}")
            update_file_status(file_id, FileStatus.ERROR)
            return
        
        # Validate each chunk structure
        for i, chunk in enumerate(gemini_chunks):
            if not isinstance(chunk, dict):
                logger.error(f"Invalid chunk at index {i} for file {file_id}: expected dict, got {type(chunk)}")
                update_file_status(file_id, FileStatus.ERROR)
                return
                
            if "chunk_id" not in chunk or "content" not in chunk:
                logger.error(f"Missing required fields in chunk at index {i} for file {file_id}: {chunk.keys()}")
                update_file_status(file_id, FileStatus.ERROR)
                return
                
            if not chunk["content"] or not chunk["content"].strip():
                logger.warning(f"Empty content in chunk at index {i} for file {file_id}")
        
        logger.info(f"Successfully validated {len(gemini_chunks)} chunks from Gemini")
        
        # Step 3: Convert Gemini chunks 
        processed_chunks = []
        for chunk in gemini_chunks:
            processed_chunks.append({
                "chunk_id": chunk["chunk_id"],
                "content": chunk["content"],
                "metadata": {
                    "file_id": file_id,
                    "parent_chunk_id": 0
                }
            })
        
        # Step 4: Create chunk objects
        # Use source if available (for txt files), otherwise fall back to file_path
        source_info = source if source else file_path
        chunk_objects = create_chunk_objects(processed_chunks, file_id, file_created_at, source_info)
        
        # Step 5: Embed and store chunks
        stored_count = embed_and_store_chunks(chunk_objects, file_id)
        logger.info(f"Successfully stored {stored_count} chunks for text document {file_id}")
        
        # Save chunk objects to log
        save_chunk_objects_to_log(chunk_objects, file_id, "txt")
        
        # Update status to processed
        update_file_status(file_id, FileStatus.PROCESSED)
        logger.info(f"Completed processing text document: {file_id}")
        
    except Exception as e:
        logger.error(f"Error processing text document: {str(e)}", exc_info=True)
        update_file_status(file_id, FileStatus.ERROR)

async def process_document(message_data: Dict[str, Any]) -> None:
    """Route document processing based on content_type"""
    file_id = message_data.get("file_id")
    file_path = message_data.get("file_path")
    content_type = message_data.get("content_type", "application/pdf")  

    if not file_id or not file_path:
        logger.error("Missing file_id or file_path in message data")
        return
    
    logger.info(f"Processing document {file_id} with content_type: {content_type}")
    
    if content_type == "application/pdf":
        await process_pdf_document(message_data)
    elif content_type == "text/plain":
        await process_txt_document(message_data)
    else:
        logger.error(f"Unsupported content_type: {content_type}")
        update_file_status(file_id, FileStatus.ERROR)

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
                # Simply set status to 'deleted' without saving previous_status
                with sqlite3.connect(str(DB_PATH)) as db_conn:
                    db_conn.execute(
                        "UPDATE files_management SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE uuid = ?",
                        (FileStatus.DELETED, file_id)
                    )
                    db_conn.commit()
                    logger.info(f"Document {file_id} marked as deleted")
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
                        update_file_status(file_id, FileStatus.PENDING)
                        logger.info(f"Document {file_id} restored to default status: pending")
            else:
                logger.error(f"Failed to update is_deleted flag in Qdrant for file {file_id}")
                
    except Exception as e:
        logger.error(f"Error processing {action} for document {file_id}: {e}")
        update_file_status(file_id, FileStatus.ERROR)

async def handle_metadata_update(message_data: Dict[str, Any]) -> None:
    """
    Handle metadata update operations for processed files.
    
    Args:
        message_data: Message data containing metadata update instructions
    """
    file_id = message_data.get("file_id")
    action = message_data.get("action")
    
    if not file_id:
        logger.error("Missing file_id in metadata update message")
        return
        
    logger.info(f"Processing metadata update for document {file_id}, action: {action}")
    
    try:
        qdrant_manager = modules.embedding_module.qdrant_manager
        
        if action == "update_metadata":
            # Update file_created_at in Qdrant
            file_created_at = message_data.get("file_created_at")
            if file_created_at:
                result = qdrant_manager.update_file_created_at_batch(file_id, file_created_at)
                if result:
                    logger.info(f"Successfully updated file_created_at for document {file_id}")
                else:
                    logger.error(f"Failed to update file_created_at in Qdrant for file {file_id}")
                    
        elif action == "update_keywords":
            # Keywords update doesn't require Qdrant changes, just log
            keywords = message_data.get("keywords", "")
            logger.info(f"Keywords update processed for document {file_id}: {keywords}")
            
        else:
            logger.error(f"Unsupported metadata update action: {action}")
                
    except Exception as e:
        logger.error(f"Error processing metadata update for document {file_id}: {e}")

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
            "update_metadata": handle_metadata_update,
            "update_keywords": handle_metadata_update,
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
            update_file_status(file_id, FileStatus.ERROR)

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
            memory_manager=modules.cuda_memory_manager
        )
        logger.info("Vietnamese Embedding Module initialized successfully")
        
        # Initialize Gmail Handler with query module for text processing
        logger.info("Initializing Gmail Handler for text processing...")
        modules.gmail_handler = GmailHandler()
        
        # Only initialize the query module, don't authenticate Gmail
        try:
            modules.gmail_handler._init_query_module()
            logger.info("Gmail Handler initialized successfully for text processing")
        except Exception as e:
            logger.error(f"Failed to initialize Gmail Handler query module: {e}")
            # Don't fail startup completely, but log the error
            modules.gmail_handler = None
            raise Exception(f"Critical: Query module initialization failed: {e}")
        
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
        client = get_rabbitmq_client()
        await client.create_subscription(
            settings.PDF_PROCESSING_TOPIC,
            "processing_service_subscription",
            handle_processing_message
        )
        logger.info("Processing subscription created successfully")
        
        # Start Gmail monitoring with dependency injection
        logger.info("Starting Gmail monitoring with shared handler...")
        asyncio.create_task(start_gmail_monitoring(gmail_handler=modules.gmail_handler))
        logger.info("Gmail monitoring started successfully")
        
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