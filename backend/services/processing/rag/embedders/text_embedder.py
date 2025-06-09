"""
Vietnamese Embedding Module with Hybrid Search
"""

import logging
from typing import List, Dict, Any, Optional, Union
import os
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
from langchain_qdrant.fastembed_sparse import FastEmbedSparse

# Import common modules using absolute imports
from backend.services.processing.rag.common.cuda import CudaMemoryManager
from backend.services.processing.rag.common.qdrant import ChunkData, QdrantManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VietnameseEmbeddingModule:
    """Module for embedding Vietnamese text with hybrid search"""
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "vietnamese_chunks",
        dense_model_name: str = "AITeamVN/Vietnamese_Embedding_v2",
        sparse_model_name: str = "Qdrant/bm25",
        vector_size: int = 1024,
        cuda_device: int = 0,
        reranker_model_name: str = "AITeamVN/Vietnamese_Reranker",
        memory_manager: Optional[CudaMemoryManager] = None
    ):
        """
        Initialize embedding module with hybrid search
        """
            
        self.dense_model_name = dense_model_name
        self.sparse_model_name = sparse_model_name
        self.vector_size = vector_size
        self.reranker_model_name = reranker_model_name
        
        # Use provided memory manager or create new one
        if memory_manager is not None:
            self.memory_manager = memory_manager
            logger.info("Using shared CUDA Memory Manager")
        else:
            self.memory_manager = CudaMemoryManager(cuda_device)
            logger.info("Created new CUDA Memory Manager")
        self.device = self.memory_manager.device
        
        # Initialize dense embedding model
        logger.info(f"Loading dense model: {dense_model_name}")
        self.dense_model = self._load_dense_model()
        
        # Initialize sparse embedding model
        logger.info(f"Loading sparse model: {sparse_model_name}")
        self.sparse_model = self._load_sparse_model()
        
        # Initialize Qdrant manager with hybrid support
        self.qdrant_manager = QdrantManager(
            host=qdrant_host,
            port=qdrant_port,
            collection_name=collection_name,
            vector_size=vector_size,
            dense_encoder=self.dense_model,
            sparse_encoder=self.sparse_model,
            reranker_model_name=self.reranker_model_name
        )
        
    def _load_dense_model(self) -> SentenceTransformer:
        """Load the dense embedding model"""
        try:
            model = SentenceTransformer(
                self.dense_model_name, 
                device=self.device
            )
            
            # Set model to eval mode
            model.eval()
            
            # Convert to half precision if CUDA is available
            if torch.cuda.is_available():
                try:
                    model.half()  # Convert to FP16 for memory efficiency
                    logger.info("✓ Dense model converted to FP16 for memory efficiency")
                except (RuntimeError, AttributeError, TypeError) as e:
                    logger.warning(f"Cannot convert dense model to FP16: {e}, using FP32")
            
            return model
            
        except Exception as e:
            logger.error(f"Error loading dense model: {e}")
            raise
            
    def _load_sparse_model(self) -> FastEmbedSparse:
        """Load the sparse embedding model"""
        try:
            model = FastEmbedSparse(model_name=self.sparse_model_name)
            logger.info("✓ Sparse model initialized successfully")
            return model
        except Exception as e:
            logger.error(f"Error loading sparse model: {e}")
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
    

    def generate_embeddings_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Generate embeddings for a batch of texts"""
        if not texts:
            return []
        
        # Preprocess texts
        processed_texts = [self._preprocess_text(text) for text in texts]
        
        try:
            # Generate dense embeddings
            with torch.no_grad():
                dense_embeddings = self.dense_model.encode(
                    processed_texts,
                    normalize_embeddings=True,
                    batch_size=min(16, len(processed_texts)),
                    device=self.device,
                    show_progress_bar=False
                )
                
                if isinstance(dense_embeddings, torch.Tensor):
                    dense_embeddings = dense_embeddings.cpu().numpy()
            
            # Generate sparse embeddings and combine with dense
            results = []
            for i, text in enumerate(processed_texts):
                try:
                    sparse_embedding = self.sparse_model.embed_query(text)
                    sparse_vector = {
                        "indices": sparse_embedding.indices,
                        "values": sparse_embedding.values
                    }
                except (RuntimeError, AttributeError, ValueError):
                    sparse_vector = {"indices": [0], "values": [0.0]}
                
                results.append({
                    "dense": dense_embeddings[i].tolist(),
                    "sparse": sparse_vector
                })
                
            return results
            
        except Exception as e:
            logger.error(f"Error in batch embedding: {e}")
            # Return zero embeddings as fallback
            return [{"dense": [0.0] * self.vector_size, "sparse": {"indices": [0], "values": [0.0]}}] * len(texts)
    
    def index_documents(self, chunks: List[ChunkData], batch_size: int = 100):
        """Index documents using hybrid vectors"""
        if not chunks:
            logger.warning("No chunks provided for indexing")
            return
            
        try:
            contents = [chunk.content for chunk in chunks if chunk.content]
            if not contents:
                logger.warning("No valid content found in chunks")
                return
                
            logger.info(f"Starting to index {len(contents)} documents")
            
            # Generate embeddings for all contents at once
            embeddings = self.generate_embeddings_batch(contents)
            
            if not embeddings:
                raise ValueError("Failed to generate embeddings")
            
            # Map embeddings back to chunks
            valid_chunks = []
            valid_embeddings = []
            content_index = 0
            
            for chunk in chunks:
                if chunk.content and content_index < len(embeddings):
                    valid_chunks.append(chunk)
                    valid_embeddings.append(embeddings[content_index])
                    content_index += 1
            
            # Store in Qdrant
            if valid_chunks:
                self.qdrant_manager.store_embeddings(valid_chunks, valid_embeddings, batch_size)
                logger.info(f"Successfully indexed {len(valid_chunks)} documents")
            else:
                raise ValueError("No valid chunks to store")
                
            # Clean up memory
            if self.memory_manager:
                self.memory_manager.cleanup_memory()
                
        except Exception as e:
            logger.error(f"Error indexing documents: {e}")
            if self.memory_manager:
                self.memory_manager.cleanup_memory()
            raise  # Re-raise to let caller handle
    
    def cleanup(self):
        """Clean up resources"""
        try:
            # Cleanup models with proper CUDA memory management
            if hasattr(self, 'dense_model') and self.dense_model is not None:
                # Move model to CPU before deletion if on CUDA
                if hasattr(self.dense_model, 'to') and torch.cuda.is_available():
                    self.dense_model.to('cpu')
                del self.dense_model
                self.dense_model = None
                
            if hasattr(self, 'sparse_model') and self.sparse_model is not None:
                del self.sparse_model
                self.sparse_model = None
                
            if hasattr(self, 'qdrant_manager') and hasattr(self.qdrant_manager, 'reranker') and self.qdrant_manager.reranker is not None:
                # Move reranker to CPU before deletion if on CUDA
                if hasattr(self.qdrant_manager.reranker, 'model') and hasattr(self.qdrant_manager.reranker.model, 'to') and torch.cuda.is_available():
                    self.qdrant_manager.reranker.model.to('cpu')
                del self.qdrant_manager.reranker
                self.qdrant_manager.reranker = None
                
            # Cleanup memory manager
            if self.memory_manager:
                self.memory_manager.cleanup_memory(force=True)
                
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            # Force garbage collection
            import gc
            gc.collect()
                
            logger.info("✓ Resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            # Still try to force cleanup even if there were errors
            try:
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass