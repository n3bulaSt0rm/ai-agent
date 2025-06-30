#!/usr/bin/env python3
"""
Script để lấy ra các chunk trong Qdrant theo file_id
"""

import sys
import logging
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Add project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from backend.common.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_chunks_by_file_id(file_id: str, collection_name: str = None):
    """Lấy chunks theo file_id từ Qdrant"""
    
    if collection_name is None:
        collection_name = settings.EMAIL_QA_COLLECTION
    
    try:
        # Connect to Qdrant
        client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        
        print(f"🔍 Searching for chunks with file_id: {file_id}")
        print(f"📁 Collection: {collection_name}")
        print("=" * 60)
        
        # Create filter for file_id
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="file_id",
                    match=MatchValue(value=file_id)
                )
            ]
        )
        
        # Search for points
        search_result = client.scroll(
            collection_name=collection_name,
            scroll_filter=search_filter,
            limit=100,  # Adjust limit as needed
            with_payload=True,
            with_vectors=False
        )
        
        points = search_result[0]  # First element is the list of points
        
        if not points:
            print(f"❌ No chunks found with file_id: {file_id}")
            return []
        
        print(f"✅ Found {len(points)} chunks with file_id: {file_id}")
        print("=" * 60)
        
        # Display chunks
        for i, point in enumerate(points, 1):
            payload = point.payload or {}
            
            print(f"\n📄 CHUNK {i}:")
            print(f"   Point ID: {point.id}")
            print(f"   File ID: {payload.get('file_id', 'N/A')}")
            print(f"   Chunk ID: {payload.get('chunk_id', 'N/A')}")
            print(f"   Source: {payload.get('source', 'N/A')}")
            print(f"   Created: {payload.get('file_created_at', 'N/A')}")
            print(f"   Content: {payload.get('content', 'N/A')[:200]}...")
            print("-" * 40)
        
        return points
        
    except Exception as e:
        logger.error(f"Error getting chunks by file_id: {e}")
        return []

def main():
    """Main function"""
    print("🔍 Qdrant Chunk Retrieval Script")
    print("=" * 60)
    
    # Target file_id
    target_file_id = "197c20e13e71011d,197c21d6b8c96c0fembedd"
    
    # Check both collections
    collections_to_check = [
        settings.EMAIL_QA_COLLECTION,
        settings.QDRANT_COLLECTION_NAME
    ]
    
    total_chunks_found = 0
    
    for collection in collections_to_check:
        print(f"\n🔍 Checking collection: {collection}")
        print("=" * 60)
        
        chunks = get_chunks_by_file_id(target_file_id, collection)
        total_chunks_found += len(chunks)
        
        if not chunks:
            print(f"   No chunks found in {collection}")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total chunks found: {total_chunks_found}")
    print(f"   Target file_id: {target_file_id}")
    
    # Also try shorter file_id (just the thread_id part)
    thread_id_only = "197c20e13e71011d,197c21d6b8c96c0f"
    print(f"\n🔍 Also checking with thread_id only: {thread_id_only}")
    
    for collection in collections_to_check:
        print(f"\n🔍 Checking collection: {collection} (thread_id only)")
        chunks = get_chunks_by_file_id(thread_id_only, collection)
        if chunks:
            print(f"   ✅ Found {len(chunks)} chunks with thread_id: {thread_id_only}")

if __name__ == "__main__":
    main() 