import nltk
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import json
import os
import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SemanticChunkingConfig:
    """Configuration for the semantic chunker"""
    threshold: float = field(default=0.3)
    model_name: str = field(default="bkai-foundation-models/vietnamese-bi-encoder")
    min_chunk_length: int = field(default=8)

class ProtonxSemanticChunker:
    def __init__(self, config: SemanticChunkingConfig):
        """
        Initialize the semantic chunker with the provided configuration.
        
        Args:
            config: Configuration for the semantic chunker
        """
        self.config = config
        self.model = self._initialize_model()
        # Download punkt for sentence tokenization, ensuring it's only done when class is initialized
        nltk.download("punkt", quiet=True)

    def _initialize_model(self) -> SentenceTransformer:
        """Initialize the SentenceTransformer model"""
        try:
            return SentenceTransformer(self.config.model_name)
        except Exception as e:
            logger.error(f"Failed to load model {self.config.model_name}: {e}")
            raise RuntimeError(f"Could not initialize model: {e}")

    def embed_function(self, sentences):
        """
        Embeds sentences using SentenceTransformer.
        """
        return self.model.encode(sentences)

    def split_text(self, text):
        """
        Split text into semantic chunks based on similarity threshold.
        
        Args:
            text: Text to split
            
        Returns:
            List of semantic chunks
        """
        if not text or not text.strip():
            logger.warning("Empty or whitespace-only text provided for splitting")
            return []
            
        sentences = nltk.sent_tokenize(text)  # Extract sentences
        sentences = [item for item in sentences if item and item.strip()]
        
        if not len(sentences):
            logger.warning("No valid sentences found after tokenization")
            return []
            
        logger.info(f"Processing {len(sentences)} sentences for semantic chunking")

        # Vectorize the sentences for similarity checking
        try:
            vectors = self.embed_function(sentences)
            logger.debug(f"Generated embeddings with shape: {vectors.shape}")
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            # Fallback: return each sentence as a separate chunk
            return [sentence.strip() for sentence in sentences if sentence.strip()]
            
        # Calculate pairwise cosine similarity between sentences
        similarities = cosine_similarity(vectors)   
        
        # Initialize chunks with the first sentence
        chunks = [[sentences[0]]]
        
        # Group sentences into chunks based on similarity threshold
        for i in range(1, len(sentences)):
            sim_score = similarities[i-1, i]
            if sim_score >= self.config.threshold:
                # If the similarity is above the threshold, add to the current chunk
                chunks[-1].append(sentences[i])
            else:
                # Start a new chunk
                chunks.append([sentences[i]])
                
        # Join the sentences in each chunk to form coherent paragraphs
        result_chunks = [' '.join(chunk) for chunk in chunks]
        logger.info(f"Created {len(result_chunks)} semantic chunks from {len(sentences)} sentences")
        
        return result_chunks
    
    def process_chunks(self, chunks: List[Dict], file_id: str) -> List[Dict]:
        """
        Process a list of chunks by further breaking them down semantically.
        
        Args:
            chunks: List of chunk dictionaries with content and metadata
            file_id: The file ID extracted from the filename
            
        Returns:
            List of refined chunks with semantic divisions and sequential chunk_ids
        """
        refined_chunks = []
        global_chunk_id = 1
        
        for parent_chunk in chunks:
            content = parent_chunk.get('content', '')
            metadata = parent_chunk.get('metadata', {})
            parent_chunk_id = parent_chunk.get('chunk_id', 0)
            
            # Skip empty content
            if not content.strip():
                continue
                
            # Apply semantic chunking to break down the content further
            semantic_chunks = self.split_text(content)
            
            # Create new refined chunks with sequential IDs
            for sem_chunk in semantic_chunks:
                sem_chunk = sem_chunk.strip()
                # Filter out chunks with content length < min_chunk_length
                if sem_chunk and len(sem_chunk) > self.config.min_chunk_length:
                    # Create minimal metadata for Qdrant storage
                    clean_metadata = {
                        "file_id": file_id,
                        "parent_chunk_id": parent_chunk_id
                    }
                    
                    refined_chunks.append({
                        "chunk_id": global_chunk_id,
                        "content": sem_chunk,
                        "metadata": clean_metadata
                    })
                    global_chunk_id += 1
                    
        return refined_chunks

def create_semantic_chunking_config(
    threshold: float = 0.3,
    model_name: str = "bkai-foundation-models/vietnamese-bi-encoder",
    min_chunk_length: int = 8
) -> SemanticChunkingConfig:
    """
    Create a configuration for semantic chunking.
    
    Args:
        threshold: Similarity threshold for chunking
        model_name: Name of the model to use
        min_chunk_length: Minimum length of a chunk
        
    Returns:
        SemanticChunkingConfig instance
    """
    return SemanticChunkingConfig(
        threshold=threshold,
        model_name=model_name,
        min_chunk_length=min_chunk_length
    ) 