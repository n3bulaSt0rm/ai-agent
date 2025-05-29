"""
Qdrant Retriever Configuration
"""

from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class RankingConfig:
    """Configuration for ranking results"""
    semantic_weight: float = 0.6
    bm25_weight: float = 0.3
    keyword_weight: float = 0.1
    similarity_threshold: float = 0.7
    min_score_threshold: float = 0.3
    
    # BM25 parameters
    bm25_k1: float = 1.5  # Used by langchain internally
    bm25_b: float = 0.75  # Used by langchain internally
    
    # Corpus statistics sampling
    corpus_sample_size: int = 500
    default_doc_count: int = 1000
    default_avgdl: float = 200
    
    # Boosting factors
    content_keyword_boost: float = 1.2
    metadata_keyword_boost: float = 1.8
    original_chunk_boost: float = 0.1
    multi_chunk_boost: float = 0.05
    
    # Adjacent chunk retrieval
    adjacent_before: int = 3
    adjacent_after: int = 3

@dataclass
class CorpusStats:
    """Store corpus statistics for BM25"""
    initialized: bool = False
    document_count: int = 0
    term_document_freq: Dict[str, int] = field(default_factory=dict)
    avgdl: float = 200.0
    doc_lengths: List[int] = field(default_factory=list)

DEFAULT_CONFIG = {
    "host": "localhost",
    "port": 6333,
    "collection_name": "hust_documents",
    "top_k": 5,
    "similarity_threshold": 0.6,
    "use_reranking": True,
    "timeout": 10.0
} 