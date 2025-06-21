import json
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from langchain.text_splitter import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChunkingConfig:
    chunk_size: int = field(default=1800)
    chunk_overlap: int = field(default=200)
    model_name: str = field(default="AITeamVN/Vietnamese_Embedding_v2")
    tokenizer_name: Optional[str] = field(default=None)
    max_sequence_length: int = field(default=2048)
    
    # Text processing parameters - Generic for all markdown documents
    separators: List[str] = field(default_factory=lambda: [
        "\n\n\n",  # Section breaks
        "\n\n",    # Paragraph breaks
        "\n",      # Line breaks
        ". ",      # Sentence ends
        "! ",      # Exclamation
        "? ",      # Question
        "; ",      # Semicolon
        ", ",      # Comma
        " ",       # Space
        ""         # Character level (last resort)
    ])
    
    min_chunk_length: int = field(default=50)
    
    def __post_init__(self):
        if self.chunk_size > self.max_sequence_length - 100:
            logger.warning(f"Chunk size {self.chunk_size} adjusted to fit model max length {self.max_sequence_length}")
            self.chunk_size = self.max_sequence_length - 100


class RecursiveChunker:
    def __init__(self, config: ChunkingConfig):
        self.config = config
        self.tokenizer = self._initialize_tokenizer()
        self.text_splitter = self._create_text_splitter()
    
    def _initialize_tokenizer(self) -> AutoTokenizer:
        tokenizer_name = self.config.tokenizer_name or self.config.model_name
        
        try:
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
            return tokenizer
        except Exception as e:
            logger.error(f"Failed to load tokenizer {tokenizer_name}: {e}")
            raise RuntimeError(f"Could not initialize tokenizer: {e}")
    
    def _create_text_splitter(self) -> RecursiveCharacterTextSplitter:
        def token_length_function(text: str) -> int:
            try:
                tokens = self.tokenizer.encode(text, add_special_tokens=False)
                return len(tokens)
            except Exception as e:
                logger.error(f"Token counting failed: {e}")
                raise RuntimeError(f"Token counting error: {e}")
        
        return RecursiveCharacterTextSplitter(
            separators=self.config.separators,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            length_function=token_length_function,
            is_separator_regex=False,
            keep_separator=True
        )
    
    def _preprocess_text(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        
        # Compile regex patterns for better performance
        MULTIPLE_NEWLINES_PATTERN = re.compile(r'\n\s*\n\s*\n+')
        WHITESPACE_PATTERN = re.compile(r'[ \t]+')
        SENTENCE_SPACING_PATTERN = re.compile(r'([.!?])([A-Z])')
        
        # Normalize whitespace while preserving structure
        text = MULTIPLE_NEWLINES_PATTERN.sub('\n\n', text)  # Normalize multiple newlines
        text = WHITESPACE_PATTERN.sub(' ', text)  # Normalize spaces and tabs
        
        # Ensure proper sentence spacing
        text = SENTENCE_SPACING_PATTERN.sub(r'\1 \2', text)
        
        return text.strip()
    
    def _validate_and_process_chunk(self, chunk: str) -> Optional[str]:
        if not chunk:
            return None
        
        chunk = chunk.strip()
        
        # Filter by minimum length
        if len(chunk) < self.config.min_chunk_length:
            return None
        
        token_count = len(self.tokenizer.encode(chunk, add_special_tokens=True))
        if token_count > self.config.max_sequence_length:
            logger.warning(f"Chunk exceeds model max length: {token_count} tokens")
            # Truncate at sentence boundary
            sentences = re.split(r'[.!?]+\s+', chunk)
            truncated_chunk = ""
            for sentence in sentences:
                test_chunk = truncated_chunk + sentence + ". "
                test_tokens = len(self.tokenizer.encode(test_chunk, add_special_tokens=True))
                if test_tokens <= self.config.max_sequence_length - 50:
                    truncated_chunk = test_chunk
                else:
                    break
            chunk = truncated_chunk.strip()
        
        return chunk if chunk.strip() else None
    
    def split_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        
        processed_text = self._preprocess_text(text)
        if not processed_text:
            return []
        
        raw_chunks = self.text_splitter.split_text(processed_text)
        
        final_chunks = []
        for chunk in raw_chunks:
            processed_chunk = self._validate_and_process_chunk(chunk)
            if processed_chunk:
                final_chunks.append(processed_chunk)
        
        return final_chunks
    
    def process_chunks(self, chunks: List[Dict], file_id: str) -> List[Dict]:
        refined_chunks = []
        global_chunk_id = 1
        
        for parent_chunk in chunks:
            content = parent_chunk.get('content', '')
            parent_chunk_id = parent_chunk.get('chunk_id', 0)
            
            if not content.strip():
                continue
            
            token_chunks = self.split_text(content)
            
            for token_chunk in token_chunks:
                if token_chunk and len(token_chunk) > self.config.min_chunk_length:
                    clean_metadata = {
                        "file_id": file_id,
                        "parent_chunk_id": parent_chunk_id,
                    }
                    
                    refined_chunks.append({
                        "chunk_id": global_chunk_id,
                        "content": token_chunk,
                        "metadata": clean_metadata
                    })
                    global_chunk_id += 1
        
        return refined_chunks

def create_chunking_config(
    chunk_size: int = 1800,
    chunk_overlap: int = 200,
    model_name: str = "AITeamVN/Vietnamese_Embedding_v2",
    min_chunk_length: int = 50,
    max_sequence_length: int = 2048
) -> ChunkingConfig:
    return ChunkingConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        model_name=model_name,
        min_chunk_length=min_chunk_length,
        max_sequence_length=max_sequence_length
    )