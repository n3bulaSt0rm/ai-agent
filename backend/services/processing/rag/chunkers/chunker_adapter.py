"""
Universal Chunker Adapter
Provides a unified interface for different chunking strategies
"""

import json
import os
import logging
from typing import List, Dict, Any, Literal, Optional

from backend.services.processing.rag.chunkers.semantic_chunker import (
    ProtonxSemanticChunker, SemanticChunkingConfig, create_semantic_chunking_config
)
from backend.services.processing.rag.chunkers.recursive_chunker import (
    RecursiveChunker, ChunkingConfig, create_chunking_config
)

logger = logging.getLogger(__name__)

class UniversalChunkerAdapter:
    """
    Universal adapter for text chunking that supports multiple chunking strategies.
    """
    def __init__(
        self, 
        chunker_type: Literal["semantic", "recursive"],
        model: str = "AITeamVN/Vietnamese_Embedding_v2",
        threshold: float = 0.3,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        min_chunk_length: int = 50,
        max_sequence_length: int = 2048
    ):
        self.chunker_type = chunker_type
        self.model = model
        self.threshold = threshold
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_length = min_chunk_length
        self.max_sequence_length = max_sequence_length
        
        #not used
        if chunker_type == "semantic":
            logger.info(f"Initializing semantic chunker with model {model} and threshold {threshold}")
            semantic_config = create_semantic_chunking_config(
                threshold=threshold,
                model_name=model,
                min_chunk_length=min_chunk_length
            )
            self.chunker = ProtonxSemanticChunker(semantic_config)
        elif chunker_type == "recursive":
            logger.info(f"Initializing recursive chunker with model {model}, size {chunk_size}, overlap {chunk_overlap}")
            recursive_config = create_chunking_config(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                model_name=model
            )
            self.chunker = RecursiveChunker(recursive_config)
        else:
            raise ValueError(f"Unsupported chunker type: {chunker_type}. Use 'semantic' or 'recursive'.")

    def split_text(self, text):
        """
        Split text into chunks using the selected chunking strategy.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        return self.chunker.split_text(text)
    
    def process_chunks(self, chunks: List[Dict], file_id: str) -> List[Dict]:
        """
        Process a list of chunks using the selected chunking strategy.
        
        Args:
            chunks: List of chunk dictionaries with content and metadata
            file_id: The file ID 
            
        Returns:
            List of refined chunks with sequential chunk_ids
        """
        return self.chunker.process_chunks(chunks, file_id)
