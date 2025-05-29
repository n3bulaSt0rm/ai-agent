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
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchText

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChunkData:
    """Class to store chunk information"""
    chunk_id: int
    content: str
    file_id: str
    parent_chunk_id: int
    keywords: List[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkData':
        """Create ChunkData from dictionary"""
        return cls(
            chunk_id=data['chunk_id'],
            content=data['content'],
            file_id=data['metadata']['file_id'],
            parent_chunk_id=data['metadata']['parent_chunk_id'],
            keywords=data['metadata'].get('keywords')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ChunkData to dictionary"""
        result = {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "file_id": self.file_id,
            "parent_chunk_id": self.parent_chunk_id,
        }
        
        if self.keywords:
            result["keywords"] = self.keywords
            
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
        collection_name: str = "vietnamese_chunks",
        vector_size: int = 768
    ):
        """Initialize Qdrant manager"""
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.vector_size = vector_size
        
        # Initialize Qdrant client
        logger.info(f"Connecting to Qdrant at {host}:{port}")
        self.client = QdrantClient(host=host, port=port)
        
        # Create collection if it doesn't exist
        self._create_collection()
        
        # Local storage for chunks
        self.chunks_data = {}
    
    def _create_collection(self):
        """Create collection in Qdrant if it doesn't exist"""
        try:
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"✓ Collection created: {self.collection_name}")
            else:
                logger.info(f"✓ Collection exists: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise
    
    def load_chunks_from_file(self, file_path: str) -> List[ChunkData]:
        """Load chunks from JSON file"""
        try:
            logger.info(f"Loading chunks from: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            chunks = []
            for item in data:
                chunk = ChunkData.from_dict(item)
                chunks.append(chunk)
                
                # Save to memory
                key = (chunk.file_id, chunk.chunk_id)
                self.chunks_data[key] = chunk
                
            logger.info(f"✓ Loaded {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error loading chunks: {e}")
            raise
    
    def store_embeddings(self, chunks: List[ChunkData], embeddings: List[List[float]], batch_size: int = 10):
        """Store embeddings in Qdrant"""
        try:
            if len(chunks) != len(embeddings):
                raise ValueError(f"Number of chunks ({len(chunks)}) does not match number of embeddings ({len(embeddings)})")
                
            total_chunks = len(chunks)
            logger.info(f"Storing {total_chunks} embeddings in Qdrant...")
            
            # Prepare points for Qdrant
            points = []
            for chunk, embedding in zip(chunks, embeddings):
                # Use UUID for unique ID
                point_id = str(uuid.uuid4())
                
                # Create payload with required fields
                payload = {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "file_id": chunk.file_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "is_deleted": False  # Default value
                }
                
                # Add any additional attributes from the chunk object
                for attr_name in dir(chunk):
                    # Skip private attributes, methods, and required fields already added
                    if (not attr_name.startswith('_') and 
                        not callable(getattr(chunk, attr_name)) and 
                        attr_name not in payload):
                        payload[attr_name] = getattr(chunk, attr_name)
                
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
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
    
    def search(self, query_vector: List[float], limit: int = 10) -> List[QueryResult]:
        """Search for similar vectors in Qdrant"""
        try:
            # Create filter to exclude deleted documents
            search_filter = Filter(
                must_not=[
                    FieldCondition(key="is_deleted", match=MatchValue(value=True))
                ]
            )
            
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
                query_filter=search_filter
            )
            
            results = []
            for hit in search_results:
                # Create metadata dictionary with required fields
                metadata = {
                    "file_id": hit.payload["file_id"],
                    "parent_chunk_id": hit.payload["parent_chunk_id"]
                }
                
                # Add any additional metadata fields from the payload
                for key, value in hit.payload.items():
                    if key not in ["chunk_id", "content", "file_id", "parent_chunk_id"]:
                        metadata[key] = value
                
                result = QueryResult(
                    chunk_id=hit.payload["chunk_id"],
                    content=hit.payload["content"],
                    score=hit.score,
                    metadata=metadata
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching in Qdrant: {e}")
            return []
    
    def get_adjacent_chunks(self, chunk_id: int, file_id: str, parent_chunk_id: int, 
                          before: int = 2, after: int = 2) -> List[ChunkData]:
        """Get adjacent chunks from Qdrant"""
        try:
            search_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="file_id", match=MatchValue(value=file_id)),
                        FieldCondition(key="parent_chunk_id", match=MatchValue(value=parent_chunk_id))
                    ]
                ),
                limit=100,
                with_payload=True
            )
            
            if not search_results or not search_results[0]:
                return []
            
            # Build chunk map
            chunk_map = {}
            for point in search_results[0]:
                payload = point.payload
                point_chunk_id = int(payload.get("chunk_id", 0))
                
                # Get keywords if present
                keywords = None
                if "keywords" in payload:
                    keywords = payload["keywords"]
                
                chunk = ChunkData(
                    chunk_id=point_chunk_id,
                    content=str(payload.get("content", "")),
                    file_id=str(payload.get("file_id", "")),
                    parent_chunk_id=int(payload.get("parent_chunk_id", 0)),
                    keywords=keywords
                )
                chunk_map[point_chunk_id] = chunk
            
            # Find adjacent chunks
            adjacent_chunks = []
            
            # Before chunks
            for i in range(before, 0, -1):
                target_id = chunk_id - i
                if target_id in chunk_map:
                    adjacent_chunks.append(chunk_map[target_id])
            
            # After chunks
            for i in range(1, after + 1):
                target_id = chunk_id + i
                if target_id in chunk_map:
                    adjacent_chunks.append(chunk_map[target_id])
            
            return adjacent_chunks
            
        except Exception as e:
            logger.error(f"Error getting adjacent chunks: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "vector_size": collection_info.config.params.vectors.size,
                "vectors_count": collection_info.vectors_count,
                "points_count": collection_info.points_count,
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}
            
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
            
            # First, get all points with this file_id
            search_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="file_id", match=MatchValue(value=file_id))
                    ]
                ),
                limit=100,
                with_payload=True
            )
            
            if not search_results or not search_results[0]:
                logger.warning(f"No points found for file_id={file_id}")
                return True  # Nothing to update
            
            # Update each point with the new is_deleted flag
            points = search_results[0]
            for point in points:
                point_id = point.id
                payload = point.payload
                
                # Update the is_deleted flag
                payload["is_deleted"] = is_deleted
                
                # Update the point in Qdrant
                self.client.set_payload(
                    collection_name=self.collection_name,
                    points=[point_id],
                    payload=payload
                )
            
            logger.info(f"✓ Successfully updated {len(points)} points for file_id={file_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating is_deleted flag: {e}")
            return False
