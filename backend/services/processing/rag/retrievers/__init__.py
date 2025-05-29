"""
Retriever modules for Vietnamese RAG System

This module contains retrievers for querying embeddings and retrieving
relevant text based on semantic similarity.
"""

# Import class chính từ file qdrant_retriever.py
from .qdrant_retriever import VietnameseQueryModule, RankingConfig

# Để code cũ không bị lỗi, có thể cung cấp một alias
QdrantRetriever = VietnameseQueryModule

# Hoặc bỏ hoàn toàn nếu không cần thiết
# from retrievers.config import DEFAULT_CONFIG 

# Xuất module cho package
__all__ = ["VietnameseQueryModule", "QdrantRetriever", "RankingConfig"]

from .query_module import VietnameseQueryModule, create_query_module
from .config import RankingConfig

__all__ = ['VietnameseQueryModule', 'create_query_module', 'RankingConfig'] 