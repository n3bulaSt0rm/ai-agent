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
        chunk_size: int = 1800,
        chunk_overlap: int = 200,
        min_chunk_length: int = 50,
        max_sequence_length: int = 2048
    ):
        """
        Initialize the adapter with specified chunker type and parameters.
        
        Args:
            chunker_type: Type of chunking strategy to use ("semantic" or "recursive")
            model: Model name to use
            threshold: Similarity threshold (used only for semantic chunking)
            chunk_size: Size of chunks (used only for recursive chunking)
            chunk_overlap: Overlap between chunks (used only for recursive chunking)
            min_chunk_length: Minimum length of a chunk (used for both)
            max_sequence_length: Maximum sequence length for tokenization (used for recursive chunking)
        """
        self.chunker_type = chunker_type
        self.model = model
        self.threshold = threshold
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_length = min_chunk_length
        self.max_sequence_length = max_sequence_length
        
        # Initialize the appropriate chunker
        if chunker_type == "semantic":
            logger.info(f"Initializing semantic chunker with model {model} and threshold {threshold}")
            semantic_config = create_semantic_chunking_config(
                threshold=threshold,
                model_name=model,
                min_chunk_length=min_chunk_length
            )
            self.chunker = ProtonxSemanticChunker(semantic_config)
        elif chunker_type == "recursive":
            logger.info(f"Initializing recursive chunker with model {model}, size {chunk_size}, overlap {chunk_overlap}, max_seq_length {max_sequence_length}")
            recursive_config = create_chunking_config(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                model_name=model,
                min_chunk_length=min_chunk_length,
                max_sequence_length=max_sequence_length
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
