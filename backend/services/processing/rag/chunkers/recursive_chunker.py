import re
from typing import List, Dict
from dataclasses import dataclass, field

from langchain.text_splitter import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer
import logging

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_PATTERN = re.compile(r'[.!?]+\s+|\.{3}\s*')

@dataclass
class ChunkingConfig:
    chunk_size: int = field(default=1000)
    chunk_overlap: int = field(default=150)
    model_name: str = field(default="AITeamVN/Vietnamese_Embedding_v2")
    separators: List[str] = field(default_factory=lambda: ["\n", ". "])


class RecursiveChunker:
    def __init__(self, config: ChunkingConfig):
        self.config = config
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        except Exception as e:
            logger.error(f"Failed to load tokenizer {config.model_name}: {e}")
            raise RuntimeError(f"Could not initialize tokenizer: {e}")
    
    def split_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        
        def token_length_function(text: str) -> int:
            return len(self.tokenizer.encode(text, add_special_tokens=False))
        
        text_splitter = RecursiveCharacterTextSplitter(
            separators=self.config.separators,
            chunk_overlap=0,
            chunk_size=self.config.chunk_size,
            length_function=token_length_function,
            is_separator_regex=False,
            keep_separator=True
        )
        
        raw_chunks = text_splitter.split_text(text)
        if len(raw_chunks) > 1:
            logger.info(f"Text split into {len(raw_chunks)} chunks, applying custom overlap")
        
        final_chunks = []
        for i, chunk in enumerate(raw_chunks):
            if not chunk.strip():
                continue
            
            processed_chunk = chunk.strip()
            
            if i > 0 and final_chunks:
                overlap_text = self._get_overlap_text(final_chunks[-1], self.config.chunk_overlap)
                if overlap_text:
                    processed_chunk = overlap_text + " " + processed_chunk
            
            final_chunks.append(processed_chunk)
        
        return final_chunks
    
    def _get_overlap_text(self, previous_chunk: str, overlap_tokens: int) -> str:
        if not previous_chunk:
            return ""
        
        sentences = SENTENCE_SPLIT_PATTERN.split(previous_chunk)
        if not sentences:
            return ""
        
        overlap = ""
        for idx in range(len(sentences) - 1, -1, -1):
            sentence = sentences[idx]
            if not sentence:
                continue
                
            candidate = sentence + ". " + overlap if overlap else sentence
            token_count = len(self.tokenizer.encode(candidate, add_special_tokens=False))
            
            if token_count <= overlap_tokens:
                overlap = candidate
            else:
                overlap = candidate
                break
        
        return overlap.strip()
    
    def process_chunks(self, chunks: List[Dict], file_id: str) -> List[Dict]:
        refined_chunks = []
        global_chunk_id = 1
        
        # DEBUG: Log detailed info about input chunks
        logger.info(f"RecursiveChunker processing {len(chunks)} chunks for file {file_id}")
        for i, chunk in enumerate(chunks):
            logger.info(f"  Chunk {i}: type={type(chunk)}, has_get={hasattr(chunk, 'get')}, has_page_content={hasattr(chunk, 'page_content')}")
            if hasattr(chunk, 'page_content'):
                logger.info(f"    - page_content length: {len(chunk.page_content) if chunk.page_content else 0}")
                logger.info(f"    - metadata: {chunk.metadata}")
            else:
                logger.info(f"    - str representation: {str(chunk)[:200]}...")
        
        for parent_idx, parent_chunk in enumerate(chunks):
            try:
                # Handle both dictionary and langchain Document objects
                if hasattr(parent_chunk, 'page_content'):
                    # This is a langchain Document object
                    content = parent_chunk.page_content or ''
                    parent_chunk_id = parent_idx + 1  # Use 1-based index for langchain Documents
                else:
                    # This is a dictionary
                    content = parent_chunk.get('content', '')
                    parent_chunk_id = parent_chunk.get('chunk_id', 0)
            except AttributeError as e:
                logger.error(f"ERROR accessing chunk attributes: {e}")
                logger.error(f"Chunk type: {type(parent_chunk)}")
                logger.error(f"Chunk attributes: {dir(parent_chunk) if hasattr(parent_chunk, '__dict__') else 'N/A'}")
                logger.error(f"Chunk str: {str(parent_chunk)[:500]}")
                raise
            
            if not content.strip():
                continue
            
            token_chunks = self.split_text(content)
            
            for token_chunk in token_chunks:
                if token_chunk:
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
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    model_name: str = "AITeamVN/Vietnamese_Embedding_v2"
) -> ChunkingConfig:
    return ChunkingConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        model_name=model_name
    )