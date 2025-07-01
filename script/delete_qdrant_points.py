#!/usr/bin/env python3
"""
Script to delete points with specific file_id from Qdrant collection
"""

import os
import sys
import logging
import asyncio
from pathlib import Path

# Add project root to path to import modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import necessary modules
from backend.common.config import settings
from backend.services.processing.rag.common.qdrant import QdrantManager
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def delete_points_by_file_id(file_id: str):
    """
    Delete all points with the specified file_id from Qdrant
    
    Args:
        file_id: The file_id to match for deletion
    """
    try:
        logger.info(f"Initializing QdrantManager to delete points with file_id: {file_id}")
        
        # Initialize QdrantManager with minimal dependencies
        qdrant_manager = QdrantManager(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            collection_name=settings.EMAIL_QA_COLLECTION,
            vector_size=settings.VECTOR_SIZE,
            dense_encoder=None,  # Not needed for deletion
            sparse_encoder=None  # Not needed for deletion
        )
        
        # Count points before deletion
        count_before = 0
        try:
            # Get points with this file_id, using pagination
            next_page_offset = None
            while True:
                search_results = qdrant_manager.client.scroll(
                    collection_name=settings.EMAIL_QA_COLLECTION,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(key="file_id", match=MatchValue(value=file_id))
                        ]
                    ),
                    limit=100,
                    with_payload=False,
                    offset=next_page_offset
                )
                
                points = search_results[0]
                next_page_offset = search_results[1]
                
                count_before += len(points)
                
                if not next_page_offset or not points:
                    break
                    
            logger.info(f"Found {count_before} points with file_id: {file_id}")
            
            if count_before == 0:
                logger.warning(f"No points found with file_id: {file_id}")
                return
                
        except Exception as e:
            logger.error(f"Error counting points: {e}")
        
        # Use the existing method to delete chunks by file_id
        result = qdrant_manager.delete_chunks_by_file_id(file_id)
        
        if result:
            logger.info(f"Successfully deleted {count_before} points with file_id: {file_id}")
        else:
            logger.error(f"Failed to delete points with file_id: {file_id}")
        
    except Exception as e:
        logger.error(f"Error deleting points: {e}")
        raise

if __name__ == "__main__":
    # Get file_id from command line or use default
    file_id = sys.argv[1] if len(sys.argv) > 1 else "197c37f314f724ca,197c3a27683dbb22"
    
    logger.info(f"Starting deletion of points with file_id: {file_id}")
    delete_points_by_file_id(file_id)
    logger.info("Script completed") 