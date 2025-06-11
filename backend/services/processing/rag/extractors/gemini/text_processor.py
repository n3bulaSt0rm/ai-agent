"""
Gemini Text Document Processor
Processes text documents via Gemini File API to create intelligent chunks

Workflow:
1. Download file content from URL to server
2. Upload file to Gemini File API → receive fileUri  
3. Use fileUri with generate_content() for intelligent chunking
4. Parse JSON response to chunks
5. Cleanup uploaded file from Gemini

Note: This uses google.generativeai function-based SDK for consistency.
"""

import json
import logging
import requests
import tempfile
import os
from typing import List, Dict, Any, Optional

import google.generativeai as genai

from backend.core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

class GeminiTextProcessor:
    """Text processor using google.generativeai SDK"""
    
    def __init__(self, api_key: str = None):
        # Get API key from parameter or environment
        self.api_key = api_key or settings.GOOGLE_API_KEY
        
        if not self.api_key:
            raise ValueError("Google API key is required.")
        
        # Configure genai with API key
        genai.configure(api_key=self.api_key)
        logger.info("Gemini Text Processor initialized with google.generativeai SDK")

    def create_chunks_from_file_url(self, file_url: str, file_id: str = None) -> List[Dict[str, Any]]:
        """
        Create chunks from text file URL using Gemini File API
        
        Args:
            file_url: URL to the text file
            file_id: ID of the file (for metadata)
        
        Returns:
            List of chunks with content and metadata
        """
        tmp_file_path = None
        uploaded_file = None
        
        try:
            # Step 1: Download file from URL
            logger.info(f"Downloading file from URL: {file_url}")
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'  # Force UTF-8 encoding for Vietnamese text
            
            # Step 2: Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8') as tmp_file:
                tmp_file.write(response.text)
                tmp_file_path = tmp_file.name
            
            logger.info(f"File saved to temporary path: {tmp_file_path}")
            
            # Step 3: Upload file to Gemini File API
            logger.info("Uploading file to Gemini File API")
            uploaded_file = genai.upload_file(tmp_file_path)
            logger.info(f"File uploaded with URI: {uploaded_file.uri}")
            
            # Wait for file to be ready
            import time
            while uploaded_file.state.name == "PROCESSING":
                logger.info("Waiting for file to be processed...")
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)
            
            # Step 4: Generate chunks using Gemini
            prompt = """
Bạn là một chuyên gia phân tích và tổ chức văn bản thông minh. Nhiệm vụ của bạn là chia văn bản thành các đoạn (chunks) tối ưu cho việc tìm kiếm và truy xuất thông tin.

## NGUYÊN TẮC CHUNKING:

### 1. Phân tích cấu trúc văn bản:
- Nhận diện tiêu đề, phần, đoạn văn chính
- Xác định ranh giới logic giữa các ý tưởng
- Giữ nguyên cấu trúc markdown nếu có

### 2. Kích thước chunk thông minh:
- Mỗi chunk: 200-600 từ (tùy thuộc nội dung)
- Chunk ngắn hơn cho thông tin quan trọng, độc lập
- Chunk dài hơn cho văn bản mô tả, giải thích liên tục

### 3. Tính độc lập của chunk:
- Mỗi chunk phải có nghĩa hoàn chỉnh khi đọc riêng lẻ
- Bao gồm đủ context để hiểu nội dung
- Tránh cắt giữa câu, định nghĩa, hoặc ví dụ

### 4. Tối ưu cho tìm kiếm:
- Mỗi chunk tập trung vào 1-2 chủ đề chính
- Giữ từ khóa quan trọng trong cùng chunk
- Chunk chứa tiêu đề nên bao gồm nội dung liên quan

### 5. Xử lý nội dung đặc biệt:
- Danh sách: nhóm các mục liên quan
- Bảng: giữ nguyên structure hoặc chuyển thành text mô tả
- Code/công thức: không tách rời
- Trích dẫn: giữ nguyên với context

## OUTPUT FORMAT:
Trả về JSON với cấu trúc sau:

{
  "analysis": {
    "total_chunks": <số>,
    "document_type": "<loại văn bản: academic/technical/narrative/report/other>",
    "main_topics": ["<chủ đề chính 1>", "<chủ đề chính 2>", "..."]
  },
  "chunks": [
    {
      "chunk_id": 0,
      "content": "<nội dung chunk>",
      "topic": "<chủ đề chính của chunk>",
      "keywords": ["<từ khóa 1>", "<từ khóa 2>", "..."],
      "chunk_type": "title/content/list/table/conclusion/other"
    }
  ]
}

## QUAN TRỌNG:
- CHỈ TRẢ VỀ JSON VALID, KHÔNG GIẢI THÍCH
- Giữ nguyên format gốc (markdown, bullets, numbers...)
- Đảm bảo không mất thông tin quan trọng
- Tối ưu cho việc semantic search
"""
            
            logger.info("Generating chunks with Gemini")
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content([uploaded_file, prompt])
            
            # Step 5: Parse response
            response_text = response.text.strip()
            logger.info(f"Received response from Gemini: {response_text}...")
            
            # Clean response and parse JSON
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            try:
                data = json.loads(response_text)
                chunks = data.get("chunks", [])
                
                if not chunks:
                    raise ValueError("No chunks found in response")
                
                logger.info(f"Successfully created {len(chunks)} chunks")
                return chunks
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response text: {response_text}")
                raise ValueError("Invalid JSON response from Gemini")
            
        except Exception as e:
            logger.error(f"Error processing file URL: {e}")
            raise
        finally:
            # Cleanup temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    logger.info("Temporary file cleaned up")
                except Exception:
                    pass
            
            # Delete uploaded file from Gemini
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                    logger.info("Uploaded file deleted from Gemini")
                except Exception:
                    pass

def process_text_document_from_url(file_url: str, file_id: str = None, api_key: str = None) -> List[Dict[str, Any]]:
    """
    Standalone function to process text document from URL
    
    Args:
        file_url: URL to the text file
        file_id: ID of the file
        api_key: Google API key (optional, will use environment variable if not provided)
    
    Returns:
        List of chunks
    """
    processor = GeminiTextProcessor(api_key=api_key)
    return processor.create_chunks_from_file_url(file_url, file_id)

 