"""
Vietnamese Embedding Module - Simplified Version
"""

import logging
from typing import List, Dict, Any, Optional, Union
import os
import torch
import numpy as np
from sentence_transformers import SentenceTransformer

# Import common modules using relative imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.cuda import CudaMemoryManager
from common.qdrant import ChunkData, QdrantManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VietnameseEmbeddingModule:
    """Module for embedding Vietnamese text"""
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "vietnamese_chunks",
        model_name: str = "bkai-foundation-models/vietnamese-bi-encoder",
        vector_size: int = 768,
        cuda_device: int = 0
    ):
        """
        Initialize embedding module
        """
        self.model_name = model_name
        self.vector_size = vector_size
        
        # Initialize CUDA memory manager
        self.memory_manager = CudaMemoryManager(cuda_device)
        self.device = self.memory_manager.device
        
        # Initialize Qdrant manager
        self.qdrant_manager = QdrantManager(
            host=qdrant_host,
            port=qdrant_port,
            collection_name=collection_name,
            vector_size=vector_size
        )
        
        # Initialize embedding model
        logger.info(f"Loading model: {model_name}")
        self.embedding_model = self._load_model()
        
    def _load_model(self) -> SentenceTransformer:
        """Load the embedding model"""
        try:
            model = SentenceTransformer(
                self.model_name, 
                device=self.device
            )
            
            # Set model to eval mode
            model.eval()
            
            # Convert to half precision if CUDA is available
            if torch.cuda.is_available():
                try:
                    model.half()  # Convert to FP16 for memory efficiency
                    logger.info("✓ Model converted to FP16 for memory efficiency")
                except Exception as e:
                    logger.warning(f"Cannot convert to FP16: {e}, using FP32")
            
            return model
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text before embedding"""
        if not text or not text.strip():
            return ""
        
        # Truncate text to avoid memory issues
        max_length = self.memory_manager.sequence_length_limit
        if len(text) > max_length:
            text = text[:max_length]
            logger.debug(f"Text truncated to {max_length} chars")
        
        return text.strip()
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        try:
            processed_text = self._preprocess_text(text)
            if not processed_text:
                return [0.0] * self.vector_size
            
            # Check memory before inference
            if self.memory_manager.should_cleanup():
                self.memory_manager.cleanup_memory()
            
            with torch.no_grad():
                embedding = self.embedding_model.encode(
                    [processed_text], 
                    convert_to_tensor=True,
                    normalize_embeddings=True,
                    device=self.device
                )
                
                # Convert to CPU to free GPU memory
                if isinstance(embedding, torch.Tensor):
                    embedding = embedding.cpu().numpy()
                
                return embedding[0].tolist()
                
        except torch.cuda.OutOfMemoryError:
            logger.error("Out of memory! Attempting recovery...")
            self.memory_manager.cleanup_memory(force=True)
            
            # Try again with shorter text
            emergency_text = text[:256] if len(text) > 256 else text
            return self.generate_embedding(emergency_text)
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * self.vector_size
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts"""
        try:
            if not texts:
                return []
            
            # Preprocess texts
            processed_texts = [self._preprocess_text(text) for text in texts]
            text_lengths = [len(text) for text in processed_texts]
            
            # Calculate optimal batch size
            optimal_batch_size = self.memory_manager.get_optimal_batch_size(text_lengths)
            
            all_embeddings = []
            total_batches = (len(processed_texts) - 1) // optimal_batch_size + 1
            
            logger.info(f"Processing {len(texts)} texts in {total_batches} batches")
            
            for i in range(0, len(processed_texts), optimal_batch_size):
                batch_texts = processed_texts[i:i + optimal_batch_size]
                
                try:
                    # Check memory before each batch
                    if self.memory_manager.should_cleanup():
                        self.memory_manager.cleanup_memory()
                    
                    with torch.no_grad():
                        batch_embeddings = self.embedding_model.encode(
                            batch_texts,
                            convert_to_tensor=True,
                            normalize_embeddings=True,
                            batch_size=len(batch_texts),
                            device=self.device,
                            show_progress_bar=False
                        )
                        
                        # Convert to CPU immediately
                        if isinstance(batch_embeddings, torch.Tensor):
                            batch_embeddings = batch_embeddings.cpu().numpy()
                        
                        all_embeddings.extend(batch_embeddings.tolist())
                        
                        # Log progress
                        batch_num = (i // optimal_batch_size) + 1
                        progress = (i + len(batch_texts)) / len(processed_texts) * 100
                        logger.info(f"Batch {batch_num}/{total_batches} - {progress:.1f}%")
                        
                except torch.cuda.OutOfMemoryError:
                    logger.error(f"OOM error, processing texts individually")
                    self.memory_manager.cleanup_memory(force=True)
                    
                    # Process each text individually
                    for text in batch_texts:
                        embedding = self.generate_embedding(text)
                        all_embeddings.append(embedding)
            
            # Final cleanup
            self.memory_manager.cleanup_memory()
            
            logger.info(f"✓ Batch embedding completed: {len(all_embeddings)} embeddings")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error in batch embedding: {e}")
            # Fallback: process one by one
            return [self.generate_embedding(text) for text in texts]
    
    def load_and_embed_chunks(self, file_path: str, keywords: List[str] = None, metadata: Dict[str, Any] = None, batch_size: int = 8):
        """
        Load chunks from file and embed them
        
        Args:
            file_path: Path to JSON file containing chunks
            keywords: List of keywords to add to metadata (optional)
            metadata: Additional metadata to add to all chunks (optional)
            batch_size: Batch size for storing embeddings
        """
        try:
            # Load chunks from file
            chunks = self.qdrant_manager.load_chunks_from_file(file_path)
            if not chunks:
                logger.warning(f"No chunks loaded from {file_path}")
                return
            
            # Add keywords to chunks metadata if provided
            if keywords and len(keywords) > 0:
                logger.info(f"Adding keywords to chunks metadata: {keywords}")
                for chunk in chunks:
                    # Add keywords as a property to chunk object
                    setattr(chunk, 'keywords', keywords)
            
            # Add additional metadata if provided
            if metadata and isinstance(metadata, dict):
                logger.info(f"Adding additional metadata to chunks: {metadata.keys()}")
                for chunk in chunks:
                    for key, value in metadata.items():
                        setattr(chunk, key, value)
            
            # Generate embeddings
            chunk_texts = [chunk.content for chunk in chunks]
            logger.info(f"Generating embeddings for {len(chunk_texts)} chunks...")
            embeddings = self.generate_embeddings_batch(chunk_texts)
            
            # Store in Qdrant
            self.qdrant_manager.store_embeddings(chunks, embeddings, batch_size)
            
            logger.info(f"✓ Successfully loaded and embedded chunks from {file_path}")
            
        except Exception as e:
            logger.error(f"Error loading and embedding chunks: {e}")
            raise
    
    def query_similar(self, query_text: str, limit: int = 10):
        """Query similar chunks"""
        try:
            # Generate embedding for query
            query_embedding = self.generate_embedding(query_text)
            
            # Search in Qdrant
            return self.qdrant_manager.search(query_embedding, limit)
            
        except Exception as e:
            logger.error(f"Error querying similar chunks: {e}")
            return []
    
    def get_info(self):
        """Get information about the embedding module and collection"""
        collection_info = self.qdrant_manager.get_collection_info()
        memory_info = self.memory_manager.get_current_usage()
        
        return {
            **collection_info,
            "model_name": self.model_name,
            "device": str(self.device),
            "memory_usage": f"{memory_info['usage_percent']:.1f}%"
        }
    
    def cleanup(self):
        """Clean up resources"""
        self.memory_manager.cleanup_memory(force=True)
        logger.info("✓ Resources cleaned up")


# Example usage
if __name__ == "__main__":
    try:
        logger.info("Initializing Vietnamese Embedding Module...")
        
        # Create embedding module
        embedding_module = VietnameseEmbeddingModule(
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name="vietnamese_chunks_test",
            model_name="bkai-foundation-models/vietnamese-bi-encoder"
        )
        
        # Load and embed chunks with keywords
        data_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                               "data/final_chunks_12f371bf-3fd8-4205-b06e-8346c8f40ad2.json")
        
        if os.path.exists(data_file):
            # Define program-specific keywords
            keywords = ["đồ án", "chương trình học", "HUST", "đại học bách khoa"]
            
            # Embed with keywords
            embedding_module.load_and_embed_chunks(
                file_path=data_file,
                keywords=keywords,
                batch_size=8
            )
        else:
            logger.error(f"Data file not found: {data_file}")
        
        # Clean up
        embedding_module.cleanup()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()