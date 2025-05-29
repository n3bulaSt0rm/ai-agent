import os
import json
import logging
import time
import numpy as np
from typing import List, Dict, Any, Optional, Union, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse
from sentence_transformers import SentenceTransformer
from backend.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

class VectorStore:
    """
    Enhanced vector store implementation using Qdrant with improved error handling,
    caching and performance optimizations.
    """
    
    def __init__(self, host: str = None, port: int = None, collection_name: str = None, 
                 model_name: str = None):
        """
        Initialize vector store with configurable settings.
        
        Args:
            host: Qdrant host (defaults to settings.QDRANT_HOST)
            port: Qdrant port (defaults to settings.QDRANT_PORT)
            collection_name: Collection name (defaults to settings.QDRANT_COLLECTION_NAME)
            model_name: Embedding model name (defaults to settings.EMBEDDING_MODEL)
        """
        # Initialize Qdrant client
        self.host = host or settings.QDRANT_HOST
        self.port = port or settings.QDRANT_PORT
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME
        
        # Connect with retries
        self.client = self._connect_with_retry(max_retries=5)
        
        # Initialize embedding model
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.model = SentenceTransformer(self.model_name)
        self.vector_size = self.model.get_sentence_embedding_dimension()
        
        # Initialize collection if it doesn't exist
        self._ensure_collection()
        
        # Embedding cache to avoid recomputing embeddings for the same text
        self._embedding_cache = {}
        self._max_cache_size = 1000  # Limit cache size to avoid memory issues
    
    def _connect_with_retry(self, max_retries: int = 5, delay: float = 1.0) -> QdrantClient:
        """
        Connect to Qdrant with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts
            delay: Delay between retries in seconds
            
        Returns:
            QdrantClient instance
            
        Raises:
            ConnectionError: If connection fails after retries
        """
        for attempt in range(max_retries):
            try:
                client = QdrantClient(host=self.host, port=self.port)
                # Test connection
                client.get_collections()
                logger.info(f"Successfully connected to Qdrant at {self.host}:{self.port}")
                return client
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Connection attempt {attempt+1} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    # Exponential backoff
                    delay *= 2
                else:
                    logger.error(f"Failed to connect to Qdrant after {max_retries} attempts")
                    raise ConnectionError(f"Could not connect to Qdrant: {e}")
    
    def _ensure_collection(self):
        """
        Ensure collection exists, create if it doesn't.
        Includes error handling and automatic retries.
        """
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating collection {self.collection_name}")
                try:
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(
                            size=self.vector_size,
                            distance=models.Distance.COSINE
                        ),
                        optimizers_config=models.OptimizersConfigDiff(
                            indexing_threshold=10000  # Optimize for bulk loading
                        )
                    )
                    logger.info(f"Collection {self.collection_name} created successfully")
                except UnexpectedResponse as e:
                    # Check if the error is because collection already exists
                    if "already exists" in str(e):
                        logger.info(f"Collection {self.collection_name} already exists")
                    else:
                        raise
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise
    
    def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text with caching.
        
        Args:
            text: Text to embed
            
        Returns:
            Vector embedding
        """
        # Check cache first
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        # Clean up cache if it gets too large
        if len(self._embedding_cache) > self._max_cache_size:
            self._embedding_cache.clear()
        
        # Generate embedding
        embedding = self.model.encode(text).tolist()
        
        # Cache the result
        self._embedding_cache[text] = embedding
        
        return embedding
    
    def _chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[Tuple[str, int, int]]:
        """
        Split text into overlapping chunks with position information.
        
        Args:
            text: Text to split
            chunk_size: Size of each chunk in characters (from settings if None)
            overlap: Overlap between chunks in characters (from settings if None)
            
        Returns:
            List of tuples (chunk_text, start_pos, end_pos)
        """
        chunk_size = chunk_size or settings.CHUNK_SIZE
        overlap = overlap or settings.CHUNK_OVERLAP
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + chunk_size, len(text))
            
            # Try to find sentence or paragraph boundary for cleaner chunks
            if end < len(text):
                for sep in [".\n", ".\r\n", ". ", "\n\n", "\r\n\r\n"]:
                    boundary = text.rfind(sep, start, end)
                    if boundary > start:
                        end = boundary + len(sep)
                        break
            
            chunks.append((text[start:end], start, end))
            start = end - overlap
        
        return chunks
    
    def index_document(self, document: Dict[str, Any], chunk_size: int = None, 
                       overlap: int = None, batch_size: int = 100) -> str:
        """
        Index a document in the vector store.
        
        Args:
            document: Document data with pages and text
            chunk_size: Size of each chunk in characters
            overlap: Overlap between chunks in characters
            batch_size: Number of vectors to insert in each batch
            
        Returns:
            Document ID in vector store
            
        Raises:
            ValueError: If document data is invalid
            ConnectionError: If Qdrant connection fails
        """
        try:
            if not document.get('file_id'):
                raise ValueError("Document must have a file_id")
                
            document_id = f"doc_{document.get('file_id', '')}"
            
            # Process each page
            all_points = []
            indexed_chunks = 0
            
            for page in document.get("pages", []):
                page_num = page.get("page_num")
                text = page.get("text", "")
                
                if not text:
                    logger.warning(f"Empty text for page {page_num} in document {document_id}")
                    continue
                
                # Split into chunks with position information
                chunks = self._chunk_text(text, chunk_size, overlap)
                
                # Process each chunk
                for i, (chunk_text, start_pos, end_pos) in enumerate(chunks):
                    # Skip empty chunks
                    if not chunk_text.strip():
                        continue
                        
                    chunk_id = f"{document_id}_p{page_num}_c{i}"
                    
                    # Generate embedding
                    try:
                        embedding = self._get_embedding(chunk_text)
                    except Exception as e:
                        logger.error(f"Error generating embedding for chunk {i} in page {page_num}: {e}")
                        continue
                    
                    # Create point for Qdrant
                    point = models.PointStruct(
                        id=chunk_id,
                        vector=embedding,
                        payload={
                            "document_id": document_id,
                            "file_id": document.get("file_id"),
                            "filename": document.get("filename"),
                            "source": document.get("source"),
                            "page": page_num,
                            "chunk": i,
                            "start_pos": start_pos,
                            "end_pos": end_pos,
                            "text": chunk_text
                        }
                    )
                    
                    all_points.append(point)
                    indexed_chunks += 1
                    
                    # Insert in batches
                    if len(all_points) >= batch_size:
                        self._insert_batch(all_points)
                        all_points = []
            
            # Insert remaining points
            if all_points:
                self._insert_batch(all_points)
            
            logger.info(f"Indexed document {document_id} with {indexed_chunks} chunks")
            
            return document_id
        except Exception as e:
            logger.error(f"Error indexing document: {e}")
            raise
    
    def _insert_batch(self, points: List[models.PointStruct]):
        """
        Insert a batch of points with error handling and retries.
        
        Args:
            points: List of points to insert
        """
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Batch insert attempt {attempt+1} failed: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Failed to insert batch after {max_retries} attempts: {e}")
                    raise
    
    def delete_document(self, document_id: str) -> bool:
        """
        Delete a document and all its chunks from the vector store.
        
        Args:
            document_id: Document ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # If document_id doesn't start with "doc_", add it
            if not document_id.startswith("doc_"):
                document_id = f"doc_{document_id}"
                
            # Delete by filter
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id)
                            )
                        ]
                    )
                )
            )
            
            logger.info(f"Deleted document {document_id} from vector store")
            return True
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False
    
    def search(self, query: str, limit: int = 5, threshold: float = 0.7,
               filter_by: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for documents matching the query.
        
        Args:
            query: Search query
            limit: Maximum number of results
            threshold: Minimum similarity score
            filter_by: Additional filters (e.g., {"file_id": 123})
            
        Returns:
            List of matching documents
        """
        try:
            # Generate query embedding
            query_vector = self._get_embedding(query)
            
            # Prepare filter if provided
            search_filter = None
            if filter_by:
                filter_conditions = []
                for key, value in filter_by.items():
                    filter_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value)
                        )
                    )
                
                if filter_conditions:
                    search_filter = models.Filter(
                        must=filter_conditions
                    )
            
            # Search Qdrant
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=threshold,
                query_filter=search_filter
            )
            
            # Format results
            formatted_results = []
            
            for result in results:
                formatted_results.append({
                    "id": result.id,
                    "score": result.score,
                    "document_id": result.payload.get("document_id"),
                    "file_id": result.payload.get("file_id"),
                    "filename": result.payload.get("filename"),
                    "page": result.payload.get("page"),
                    "text": result.payload.get("text"),
                    "source": result.payload.get("source")
                })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []
    
    def get_document_stats(self, document_id: str) -> Dict[str, Any]:
        """
        Get statistics about a document in the vector store.
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with statistics
        """
        if not document_id.startswith("doc_"):
            document_id = f"doc_{document_id}"
            
        try:
            # Count chunks for this document
            count = self.client.count(
                collection_name=self.collection_name,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            )
            
            # Get sample chunks to find page range
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=[0.0] * self.vector_size,  # Dummy vector for scrolling
                limit=1,
                score_threshold=0.0,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            )
            
            if results and count.count > 0:
                return {
                    "document_id": document_id,
                    "chunk_count": count.count,
                    "file_id": results[0].payload.get("file_id"),
                    "filename": results[0].payload.get("filename"),
                    "status": "indexed"
                }
            else:
                return {
                    "document_id": document_id,
                    "chunk_count": 0,
                    "status": "not_found"
                }
        except Exception as e:
            logger.error(f"Error getting document stats for {document_id}: {e}")
            return {
                "document_id": document_id,
                "status": "error",
                "error": str(e)
            }

# Create singleton instance
_vector_store_instance = None

def get_vector_store() -> VectorStore:
    """Get the vector store instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance 

async def get_vector_store_async():
    """
    Get the vector store instance asynchronously.
    This is a wrapper around get_vector_store() for async compatibility.
    
    Returns:
        VectorStore instance
    """
    # Reuse the synchronous function 
    return get_vector_store() 