"""
Qdrant Operations Module
"""

import json
import logging
import uuid
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

import numpy as np
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchText, SparseVectorParams, Modifier, NamedSparseVector, SparseVector
from sentence_transformers import CrossEncoder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChunkData:
    """Class to store chunk information"""
    chunk_id: int
    content: str
    file_id: str
    parent_chunk_id: int
    file_created_at: Optional[str] = None
    source: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkData':
        """Create ChunkData from dictionary"""
        return cls(
            chunk_id=data['chunk_id'],
            content=data['content'],
            file_id=data['metadata']['file_id'],
            parent_chunk_id=data['metadata']['parent_chunk_id'],
            source=data['metadata'].get('source')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ChunkData to dictionary"""
        result = {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "file_id": self.file_id,
            "parent_chunk_id": self.parent_chunk_id,
        }
        
        if self.file_created_at:
            result["file_created_at"] = self.file_created_at
            
        if self.source:
            result["source"] = self.source
        
        return result

@dataclass
class QueryResult:
    """Class to store query result"""
    chunk_id: int
    content: str
    score: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert QueryResult to dictionary"""
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata
        }

class QdrantManager:
    """Manages Qdrant operations"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "vietnamese_chunks_test",
        vector_size: int = 1024,
        dense_encoder = "AITeamVN/Vietnamese_Embedding_v2",
        sparse_encoder = "Qdrant/bm25",
        reranker_model_name: str = "AITeamVN/Vietnamese_Reranker"
    ):
        """Initialize Qdrant manager"""
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        
        # Initialize reranker if model name is provided
        self.reranker_model_name = reranker_model_name
        self.reranker = None
        self._load_reranker()
        
        # Initialize Qdrant client
        logger.info(f"Connecting to Qdrant at {host}:{port}")
        self.client = QdrantClient(host=host, port=port)
        
        # Create collection if it doesn't exist
        self._create_collection()
    
    def _load_reranker(self):
        """Load the reranker model"""
        if not self.reranker_model_name:
            return
            
        try:
            logger.info(f"Loading reranker model: {self.reranker_model_name}")
            
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.reranker = CrossEncoder(self.reranker_model_name, device=device)
            
            # Set model to eval mode
            self.reranker.model.eval()
            
            # Convert to half precision if CUDA is available
            if torch.cuda.is_available():
                try:
                    self.reranker.model.half()
                    logger.info("Reranker model converted to FP16 for memory efficiency")
                except (RuntimeError, AttributeError, TypeError) as e:
                    logger.warning(f"Cannot convert reranker model to FP16: {e}, using FP32")
            
            logger.info("Reranker initialized successfully")
                    
        except Exception as e:
            logger.error(f"Error loading reranker model: {e}")
            self.reranker = None
    
    def _create_collection(self):
        """Create collection in Qdrant if it doesn't exist"""
        try:
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                
                # Use hybrid configuration with dense and sparse vectors
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=self.vector_size,
                            distance=Distance.DOT
                        )
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            modifier=Modifier.IDF
                        )
                    },
                )
                    
                logger.info(f"✓ Collection created: {self.collection_name}")
            else:
                logger.info(f"✓ Collection exists: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise
    
    def create_dense_vector(self, text: str) -> List[float]:
        """Create dense vector embedding from text"""
        if not self.dense_encoder:
            raise ValueError("Dense encoder not initialized")
        
        try:
            with torch.no_grad():
                vector = self.dense_encoder.encode(text, normalize_embeddings=True)
                if isinstance(vector, torch.Tensor):
                    vector = vector.cpu().tolist()
                return vector
                
        except torch.cuda.OutOfMemoryError:
            # Handle out of memory by using shorter text
            emergency_text = text[:256] if len(text) > 256 else text
            with torch.no_grad():
                vector = self.dense_encoder.encode(emergency_text, normalize_embeddings=True)
                if isinstance(vector, torch.Tensor):
                    vector = vector.cpu().tolist()
                return vector
        except Exception as e:
            logger.error(f"Error creating dense vector: {e}")
            raise
    
    def create_sparse_vector(self, text: str) -> Dict[str, Any]:
        """Create sparse vector embedding from text"""
        if not self.sparse_encoder:
            raise ValueError("Sparse encoder not initialized")
        
        try:
            sparse_embedding = self.sparse_encoder.embed_query(text)
            
            # Ensure indices and values are not empty, which can cause Qdrant API errors
            if not sparse_embedding.indices or len(sparse_embedding.indices) == 0:
                logger.warning("Sparse embedding returned empty indices")
                return {"indices": [0], "values": [0.0]}
                
            return {
                "indices": sparse_embedding.indices,
                "values": sparse_embedding.values
            }
        except Exception as e:
            logger.error(f"Error creating sparse vector for text '{text[:50]}...': {e}")
            return {"indices": [0], "values": [0.0]}
    
    def store_embeddings(self, chunks: List[ChunkData], embeddings: Optional[List[Dict[str, Any]]] = None, batch_size: int = 10):
        """Store embeddings in Qdrant"""
        try:
            # Validate inputs
            if not chunks:
                raise ValueError("No chunks provided")
                
            if embeddings and len(chunks) != len(embeddings):
                raise ValueError(f"Number of chunks ({len(chunks)}) does not match number of embeddings ({len(embeddings)})")
                
            total_chunks = len(chunks)
            logger.info(f"Storing {total_chunks} embeddings in Qdrant...")
            
            # Prepare points for Qdrant
            points = []
            
            for i, chunk in enumerate(chunks):
                # Create payload with required fields
                payload = {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "file_id": chunk.file_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "is_deleted": False  # Default value
                }
                
                # Add source if available
                if hasattr(chunk, 'source') and chunk.source:
                    payload["source"] = chunk.source
                
                # Add any additional attributes from the chunk object
                for attr_name in dir(chunk):
                    # Skip private attributes, methods, and required fields already added
                    if (not attr_name.startswith('_') and 
                        not callable(getattr(chunk, attr_name)) and 
                        attr_name not in payload):
                        payload[attr_name] = getattr(chunk, attr_name)
                
                # Use UUID for unique ID
                point_id = str(uuid.uuid4())

                # Generate embeddings if needed
                if not embeddings:
                    content = chunk.content
                    
                    if not content:
                        logger.warning(f"Empty content for chunk {chunk.chunk_id}, skipping")
                        continue
                        
                    try:
                        dense_vector = self.create_dense_vector(content)
                        sparse_vector = self.create_sparse_vector(content)
                        
                        point = PointStruct(
                            id=point_id,
                            vector={
                                "dense": dense_vector,
                                "sparse": sparse_vector
                            },
                            payload=payload
                        )
                    except Exception as e:
                        logger.error(f"Error creating vectors for chunk {chunk.chunk_id}: {e}")
                        continue
                else:
                    # Use provided embeddings
                    if isinstance(embeddings[i], dict) and "dense" in embeddings[i]:
                        # Hybrid embeddings
                        point = PointStruct(
                            id=point_id,
                            vector=embeddings[i],
                            payload=payload
                        )
                    else:
                        # Dense-only embeddings
                        point = PointStruct(
                            id=point_id,
                            vector=embeddings[i],
                            payload=payload
                        )
                
                points.append(point)
            
            # Upload to Qdrant in batches
            total_batches = (len(points) - 1) // batch_size + 1
            
            for batch_idx in range(0, len(points), batch_size):
                batch = points[batch_idx:batch_idx + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                batch_num = (batch_idx // batch_size) + 1
                logger.info(f"Uploaded batch {batch_num}/{total_batches}")
                
            logger.info(f"✓ Successfully stored {len(points)} embeddings in Qdrant")
                
        except Exception as e:
            logger.error(f"Error storing embeddings: {e}")
            raise
    
    def hybrid_search(
        self, 
        query: str, 
        candidates_limit: int = 10,
        candidates_multiplier: int = 3
    ) -> Dict[str, Any]:
        if not query.strip():
            return {
                "dense_results": [],
                "sparse_results": [],
                "query": query
            }
        
        if not self.dense_encoder:
            raise ValueError("Dense encoder is required for hybrid search")
        if not self.sparse_encoder:
            raise ValueError("Sparse encoder is required for hybrid search")
        
        try:

            first_stage_limit = candidates_limit * candidates_multiplier
            search_filter = Filter(
                must_not=[
                    FieldCondition(key="is_deleted", match=MatchValue(value=True))
                ]
            )
            dense_vector = self.create_dense_vector(query)
            sparse_vector = self.create_sparse_vector(query)
            
            dense_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=("dense", dense_vector),
                limit=first_stage_limit,
                with_payload=True,
                query_filter=search_filter
            )
            if not sparse_vector["indices"] or len(sparse_vector["indices"]) == 0:
                sparse_vector = {"indices": [0], "values": [0.0]}
            
            sparse_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=NamedSparseVector(
                    name="sparse",
                    vector=SparseVector(
                        indices=sparse_vector["indices"],
                        values=sparse_vector["values"]
                    )
                ),
                limit=first_stage_limit,
                with_payload=True,
                query_filter=search_filter
            )
            
            return {
                "dense_results": dense_results,
                "sparse_results": sparse_results,
                "query": query
            }
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            raise ValueError(f"Hybrid search failed: {e}")
            
    def update_is_deleted_flag(self, file_id: str, is_deleted: bool = True) -> bool:
        """
        Update the is_deleted flag for all vectors associated with a file_id
        
        Args:
            file_id: The file ID to update
            is_deleted: Whether to mark as deleted (True) or not deleted (False)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Updating is_deleted={is_deleted} for file_id={file_id}")
            
            # Implement pagination to process all points
            next_page_offset = None
            total_updated = 0
            batch_size = 100  # Process in smaller batches for efficiency
            
            while True:
                # Get points with this file_id, using pagination
                search_results = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(key="file_id", match=MatchValue(value=file_id))
                        ]
                    ),
                    limit=300,
                    with_payload=True,
                    offset=next_page_offset
                )
                
                points = search_results[0]
                next_page_offset = search_results[1]
                
                if not points:
                    if total_updated == 0:
                        logger.warning(f"No points found for file_id={file_id}")
                    break  # No more points to process
                
                # Process points in batches to avoid overwhelming Qdrant
                point_batches = [points[i:i + batch_size] for i in range(0, len(points), batch_size)]
                
                for batch in point_batches:
                    point_ids = []
                    payloads = []
                    
                    for point in batch:
                        point_id = point.id
                        payload = point.payload.copy()  # Create a copy to avoid modifying original
                        
                        # Update the is_deleted flag
                        payload["is_deleted"] = is_deleted
                        
                        point_ids.append(point_id)
                        payloads.append(payload)
                    
                    # Batch update all points in this batch
                    try:
                        for point_id, payload in zip(point_ids, payloads):
                            self.client.set_payload(
                                collection_name=self.collection_name,
                                points=[point_id],
                                payload=payload
                            )
                        
                        total_updated += len(batch)
                        logger.debug(f"Updated batch of {len(batch)} points for file_id={file_id}")
                        
                    except Exception as batch_error:
                        logger.error(f"Error updating batch for file_id={file_id}: {batch_error}")
                        # Continue with next batch instead of failing completely
                        continue
                
                logger.info(f"Updated {len(points)} points in current page for file_id={file_id}")
                
                # If no next page offset is returned, we've processed all points
                if not next_page_offset:
                    break
            
            logger.info(f"✓ Successfully updated {total_updated} points for file_id={file_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating is_deleted flag: {e}")
            return False

    def update_file_created_at_batch(self, file_id: str, file_created_at: str) -> bool:
        """
        Update the file_created_at field for all vectors associated with a file_id
        
        Args:
            file_id: The file ID to update
            file_created_at: The file creation timestamp to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Updating file_created_at={file_created_at} for file_id={file_id}")
            
            # Implement pagination to process all points
            next_page_offset = None
            total_updated = 0
            batch_size = 100  # Process in smaller batches for efficiency
            
            while True:
                # Get points with this file_id, using pagination
                search_results = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(key="file_id", match=MatchValue(value=file_id))
                        ]
                    ),
                    limit=300,
                    with_payload=True,
                    offset=next_page_offset
                )
                
                points = search_results[0]
                next_page_offset = search_results[1]
                
                if not points:
                    if total_updated == 0:
                        logger.warning(f"No points found for file_id={file_id}")
                    break  # No more points to process
                
                # Process points in batches to avoid overwhelming Qdrant
                point_batches = [points[i:i + batch_size] for i in range(0, len(points), batch_size)]
                
                for batch in point_batches:
                    point_ids = []
                    payloads = []
                    
                    for point in batch:
                        point_id = point.id
                        payload = point.payload.copy()  # Create a copy to avoid modifying original
                        
                        # Update the file_created_at field
                        payload["file_created_at"] = file_created_at
                        
                        point_ids.append(point_id)
                        payloads.append(payload)
                    
                    # Batch update all points in this batch
                    try:
                        for point_id, payload in zip(point_ids, payloads):
                            self.client.set_payload(
                                collection_name=self.collection_name,
                                points=[point_id],
                                payload=payload
                            )
                        
                        total_updated += len(batch)
                        logger.debug(f"Updated batch of {len(batch)} points for file_id={file_id}")
                        
                    except Exception as batch_error:
                        logger.error(f"Error updating batch for file_id={file_id}: {batch_error}")
                        # Continue with next batch instead of failing completely
                        continue
                
                logger.info(f"Updated {len(points)} points in current page for file_id={file_id}")
                
                # If no next page offset is returned, we've processed all points
                if not next_page_offset:
                    break
            
            logger.info(f"✓ Successfully updated file_created_at for {total_updated} points of file_id={file_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating file_created_at: {e}")
            return False

    def delete_chunks_by_file_id(self, file_id: str) -> bool:
        """
        Delete all chunks associated with a specific file_id
        
        Args:
            file_id: The file ID whose chunks should be deleted
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Deleting all chunks for file_id={file_id}")
            
            # Implement pagination to process all points
            next_page_offset = None
            total_deleted = 0
            batch_size = 100  # Process in smaller batches for efficiency
            
            while True:
                # Get points with this file_id, using pagination
                search_results = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(key="file_id", match=MatchValue(value=file_id))
                        ]
                    ),
                    limit=300,
                    with_payload=True,
                    offset=next_page_offset
                )
                
                points = search_results[0]
                next_page_offset = search_results[1]
                
                if not points:
                    if total_deleted == 0:
                        logger.info(f"No chunks found for file_id={file_id}")
                    break  # No more points to process
                
                # Process points in batches to avoid overwhelming Qdrant
                point_batches = [points[i:i + batch_size] for i in range(0, len(points), batch_size)]
                
                for batch in point_batches:
                    point_ids = [point.id for point in batch]
                    
                    # Delete points in this batch
                    try:
                        self.client.delete(
                            collection_name=self.collection_name,
                            points_selector=point_ids
                        )
                        
                        total_deleted += len(batch)
                        logger.debug(f"Deleted batch of {len(batch)} chunks for file_id={file_id}")
                        
                    except Exception as batch_error:
                        logger.error(f"Error deleting batch for file_id={file_id}: {batch_error}")
                        # Continue with next batch instead of failing completely
                        continue
                
                logger.info(f"Deleted {len(points)} chunks in current page for file_id={file_id}")
                
                # If no next page offset is returned, we've processed all points
                if not next_page_offset:
                    break
            
            logger.info(f"✓ Successfully deleted {total_deleted} chunks for file_id={file_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting chunks by file_id: {e}")
            return False

    def cleanup_old_email_chunks(self, cutoff_date: str) -> bool:
        """
        Delete email chunks older than cutoff date based on file_created_at
        
        Args:
            cutoff_date: ISO format cutoff date string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Cleaning up email chunks older than {cutoff_date}")
            
            # Implement pagination to process all points
            next_page_offset = None
            total_deleted = 0
            batch_size = 100  # Process in smaller batches for efficiency
            
            while True:
                # Get all email chunks (source = "gmail_thread")
                search_results = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(key="source", match=MatchValue(value="gmail_thread"))
                        ]
                    ),
                    limit=300,
                    with_payload=True,
                    offset=next_page_offset
                )
                
                points = search_results[0]
                next_page_offset = search_results[1]
                
                if not points:
                    if total_deleted == 0:
                        logger.info("No email chunks found for cleanup")
                    break  # No more points to process
                
                # Filter points that are older than cutoff_date
                old_points = []
                for point in points:
                    file_created_at = point.payload.get("file_created_at")
                    if file_created_at and file_created_at < cutoff_date:
                        old_points.append(point)
                
                if not old_points:
                    logger.debug(f"No old chunks found in current page (checked {len(points)} chunks)")
                    # If no next page offset is returned, we've processed all points
                    if not next_page_offset:
                        break
                    continue
                
                # Process old points in batches
                point_batches = [old_points[i:i + batch_size] for i in range(0, len(old_points), batch_size)]
                
                for batch in point_batches:
                    point_ids = [point.id for point in batch]
                    
                    # Delete points in this batch
                    try:
                        self.client.delete(
                            collection_name=self.collection_name,
                            points_selector=point_ids
                        )
                        
                        total_deleted += len(batch)
                        logger.debug(f"Deleted batch of {len(batch)} old email chunks")
                        
                    except Exception as batch_error:
                        logger.error(f"Error deleting old email chunks batch: {batch_error}")
                        # Continue with next batch instead of failing completely
                        continue
                
                logger.info(f"Processed {len(points)} chunks, deleted {len(old_points)} old chunks in current page")
                
                # If no next page offset is returned, we've processed all points
                if not next_page_offset:
                    break
            
            logger.info(f"✓ Successfully cleaned up {total_deleted} old email chunks (older than {cutoff_date})")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up old email chunks: {e}")
            return False

    def delete_chunks_by_embedding_id(self, embedding_id: str) -> bool:
        """
        Delete all chunks associated with a specific embedding_id
        
        Args:
            embedding_id: The embedding ID whose chunks should be deleted
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Deleting all chunks for embedding_id={embedding_id}")
            
            # Implement pagination to process all points
            next_page_offset = None
            total_deleted = 0
            batch_size = 100  # Process in smaller batches for efficiency
            
            while True:
                # Get points with this embedding_id (stored as file_id in chunks)
                search_results = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(key="file_id", match=MatchValue(value=embedding_id))
                        ]
                    ),
                    limit=300,
                    with_payload=True,
                    offset=next_page_offset
                )
                
                points = search_results[0]
                next_page_offset = search_results[1]
                
                if not points:
                    if total_deleted == 0:
                        logger.info(f"No chunks found for embedding_id={embedding_id}")
                    break  # No more points to process
                
                # Process points in batches to avoid overwhelming Qdrant
                point_batches = [points[i:i + batch_size] for i in range(0, len(points), batch_size)]
                
                for batch in point_batches:
                    point_ids = [point.id for point in batch]
                    
                    # Delete points in this batch
                    try:
                        self.client.delete(
                            collection_name=self.collection_name,
                            points_selector=point_ids
                        )
                        
                        total_deleted += len(batch)
                        logger.debug(f"Deleted batch of {len(batch)} chunks for embedding_id={embedding_id}")
                        
                    except Exception as batch_error:
                        logger.error(f"Error deleting batch for embedding_id={embedding_id}: {batch_error}")
                        # Continue with next batch instead of failing completely
                        continue
                
                logger.info(f"Deleted {len(points)} chunks in current page for embedding_id={embedding_id}")
                
                # If no next page offset is returned, we've processed all points
                if not next_page_offset:
                    break
            
            logger.info(f"✓ Successfully deleted {total_deleted} chunks for embedding_id={embedding_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting chunks by embedding_id: {e}")
            return False
