from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
import os
import re
from typing import List, Dict, Optional, Tuple
import json
from langdetect import detect, detect_langs
from langdetect.lang_detect_exception import LangDetectException
from langdetect.detector_factory import DetectorFactory

DetectorFactory.seed = 0

class MarkdownChunker:
    def __init__(
        self,
        headers_to_split_on: Optional[List[Tuple[str, str]]] = None
    ):
        if headers_to_split_on is None:
            self.headers_to_split_on = [
                ("#", "heading1"),
                ("##", "heading2"),
                ("###", "heading3")
            ]
        else:
            self.headers_to_split_on = headers_to_split_on
        
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on
        )
        
        self.newline_pattern = re.compile(r'(?<!\.)(\n)')
    
    def is_header(self, line: str) -> bool:
        """Check if line is a markdown header"""
        return line.strip().startswith('#')
    
    def get_header_level(self, line: str) -> int:
        """Get the level of a markdown header (number of #)"""
        stripped = line.strip()
        if not stripped.startswith('#'):
            return 0
        return len(stripped) - len(stripped.lstrip('#'))
    
    def remove_header_prefix(self, line: str) -> str:
        """Remove # prefix from header line"""
        stripped = line.strip()
        if not stripped.startswith('#'):
            return stripped
        return stripped.lstrip('#').strip()
    
    def has_vietnamese_words(self, line: str) -> bool:
        line_stripped = line.strip()
        if not line_stripped:
            return False

        try:
            langs = detect_langs(line_stripped)
            for lang in langs:
                if lang.lang == 'vi' and lang.prob >= 0.1:
                    return True
            return False
        except LangDetectException:
            return False
    
    def has_id_or_vietnamese(self, line: str) -> bool:
        line_stripped = line.strip()
        if not line_stripped:
            return False
            
        words = line_stripped.split()
        
        for word in words:
            clean_word = ''.join(char for char in word if char.isalpha())
            if clean_word:
                try:
                    detected_lang = detect(clean_word)
                    if detected_lang in ('vi', 'id'):
                        return True
                except LangDetectException:
                    continue
        
        return False
    
    def merge_paragraph_lines(self, text: str) -> str:
        """Merge consecutive non-empty, non-header lines into paragraphs."""
        lines = text.split('\n')
        result = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()
            
            if not line_stripped:
                result.append(line)
                i += 1
                continue
            
            if self.is_header(line_stripped):
                result.append(line)
                i += 1
                continue
            
            paragraph_lines = [line.strip()]
            
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_line_stripped = next_line.strip()
                
                if not next_line_stripped:
                    break
                    
                if self.is_header(next_line_stripped):
                    break
                
                paragraph_lines.append(next_line.strip())
                j += 1
            
            merged_content = ' '.join(paragraph_lines)
            result.append(merged_content)
            i = j
        
        return '\n'.join(result)
    
    def merge_consecutive_headers(self, text: str) -> str:
        """Merge consecutive headers of same level with no content between them."""
        lines = text.split('\n')
        result = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()
            
            if self.is_header(line_stripped):
                level = self.get_header_level(line_stripped)
                merged = False
                
                for j in range(i + 1, len(lines)):
                    next_line_stripped = lines[j].strip()
                    if not next_line_stripped:
                        continue
                    
                    if self.is_header(next_line_stripped):
                        if self.get_header_level(next_line_stripped) == level:
                            first_content = self.remove_header_prefix(line_stripped)
                            second_content = self.remove_header_prefix(next_line_stripped)
                            merged_line = '#' * level + ' ' + first_content + ' ' + second_content
                            
                            result.append(merged_line)
                            result.extend(lines[i+1:j])
                            i = j + 1
                            merged = True
                            break
                    else:
                        break
                
                if not merged:
                    result.append(lines[i])
                    i += 1
            else:
                result.append(lines[i])
                i += 1
        
        return '\n'.join(result)

    def filter_vietnamese_content(self, text: str) -> str:
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if self.is_header(line_stripped):
                if self.has_id_or_vietnamese(line):
                    filtered_lines.append(line)
            else:
                if self.has_vietnamese_words(line):
                    filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    def post_process_chunks(self, chunks: List[Dict]) -> List[Dict]:
        processed_chunks = []
        
        for chunk in chunks:
            content = chunk.page_content
            
            heading_context = ""
            if chunk.metadata:
                if "heading3" in chunk.metadata:
                    heading_context = f"{chunk.metadata['heading3']} "
                elif "heading2" in chunk.metadata:
                    heading_context = f"{chunk.metadata['heading2']} "
                elif "heading1" in chunk.metadata:
                    heading_context = f"{chunk.metadata['heading1']} "
            
            clean_content = self.newline_pattern.sub(' ', content)
            final_content = heading_context + clean_content if heading_context else clean_content
            
            processed_chunks.append(Document(
                page_content=final_content,
                metadata=chunk.metadata
            ))
        
        return processed_chunks
    
    def chunk_text(self, text: str) -> List[Dict]:
        paragraph_merged = self.merge_paragraph_lines(text)
        header_merged = self.merge_consecutive_headers(paragraph_merged)
        filtered_text = self.filter_vietnamese_content(header_merged)
        header_splits = self.header_splitter.split_text(filtered_text)
        
        processed_chunks = self.post_process_chunks(header_splits)
        
        return processed_chunks