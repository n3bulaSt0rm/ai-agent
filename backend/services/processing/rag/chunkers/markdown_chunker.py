from langchain_text_splitters import MarkdownHeaderTextSplitter
import os
from typing import List, Dict, Optional, Tuple
import json
from datetime import datetime
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

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
    
    def has_vietnamese_words(self, line: str) -> bool:
        """Kiểm tra xem dòng có chứa từ tiếng Việt hay không"""
        line = line.strip()
        if not line:
            return False

        words = line.split()
        
        # Kiểm tra từng từ
        for word in words:
            # Loại bỏ các ký tự đặc biệt để chỉ lấy text thuần
            clean_word = ''.join(char for char in word if char.isalpha())
            if clean_word:
                try:
                    # Sử dụng langdetect để phát hiện ngôn ngữ
                    detected_lang = detect(clean_word)
                    if detected_lang == 'vi':
                        return True
                except LangDetectException:
                    # Nếu không thể phát hiện ngôn ngữ, bỏ qua từ này
                    continue
        
        return False
    
    def filter_vietnamese_content(self, text: str) -> str:
        """Lọc các dòng chứa ít nhất 1 từ tiếng Việt"""
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            if self.has_vietnamese_words(line):
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    def chunk_text(self, text: str) -> List[Dict]:
        # Lọc chỉ giữ lại các dòng có ít nhất 1 từ tiếng Việt
        filtered_text = self.filter_vietnamese_content(text)
        header_splits = self.header_splitter.split_text(filtered_text)
        
        serializable_chunks = []
        for i, chunk in enumerate(header_splits):
            content = chunk.page_content

            heading_context = ""
            if chunk.metadata:
                if "heading3" in chunk.metadata:
                    heading_context = f"### {chunk.metadata['heading3']}\n"
                elif "heading2" in chunk.metadata:
                    heading_context = f"## {chunk.metadata['heading2']}\n"
                elif "heading1" in chunk.metadata:
                    heading_context = f"# {chunk.metadata['heading1']}\n"
            
            final_content = heading_context + content if heading_context else content
            
            chunk_data = {
                "chunk_id": i + 1,
                "content": final_content,
                "metadata": chunk.metadata
            }
            serializable_chunks.append(chunk_data)
    
        return serializable_chunks