"""
Gemini Email Processor for Gmail Background Worker
Handles both images and PDFs with proper file management and cleanup
"""

import logging
import tempfile
import os
from typing import List, Dict, Any, Optional
import json

import google.generativeai as genai

# Setup logging
logger = logging.getLogger(__name__)

class GeminiEmailProcessor:
    """Unified processor for Gmail emails with attachments using google.generativeai SDK"""
    
    def __init__(self, api_key: str = None):
        # Get API key from parameter or environment
        self.api_key = api_key or os.environ.get('GOOGLE_API_KEY')
        
        if not self.api_key:
            raise ValueError("Google API key is required. Set GOOGLE_API_KEY environment variable or pass api_key parameter.")
        
        # Configure genai with API key
        genai.configure(api_key=self.api_key)
        logger.info("Gemini Email Processor initialized with google.generativeai SDK")

    def process_email_with_attachments(
        self, 
        email_text: str, 
        image_attachments: List[Dict[str, Any]] = None,
        pdf_attachments: List[Dict[str, Any]] = None
    ) -> str:
        """
        Process email with image and PDF attachments using Gemini
        
        Args:
            email_text: The email content
            image_attachments: List of image attachment data
            pdf_attachments: List of PDF attachment data
        
        Returns:
            Processed content string
        """
        try:
            processed_parts = [email_text]
            uploaded_files = []  # Track uploaded files for cleanup
            temp_files = []     # Track temp files for cleanup
            
            # Process image attachments
            if image_attachments:
                for i, img_attachment in enumerate(image_attachments, 1):
                    try:
                        logger.info(f"Processing image attachment {i}/{len(image_attachments)}")
                        
                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', mode='wb') as tmp_file:
                            tmp_file.write(img_attachment['data'])
                            tmp_file_path = tmp_file.name
                            temp_files.append(tmp_file_path)
                        
                        logger.info(f"Image saved to temporary file: {tmp_file_path}")
                        
                        # Upload to Gemini File API
                        uploaded_file = genai.upload_file(tmp_file_path)
                        uploaded_files.append(uploaded_file)
                        logger.info(f"Image uploaded to Gemini with URI: {uploaded_file.uri}")
                        
                        # Wait for file to be ready
                        import time
                        while uploaded_file.state.name == "PROCESSING":
                            logger.info("Waiting for image to be processed...")
                            time.sleep(2)
                            uploaded_file = genai.get_file(uploaded_file.name)
                        
                        # Generate description with Gemini
                        model = genai.GenerativeModel("gemini-2.0-flash")
                        response = model.generate_content([
                            uploaded_file,
                            "Hãy mô tả chi tiết hình ảnh này trong email. Tập trung vào nội dung quan trọng, văn bản có thể đọc được, và thông tin hữu ích cho người đọc email."
                        ])
                        
                        processed_parts.append(f"\n--- Hình ảnh đính kèm {i} ---\n{response.text}")
                        logger.info(f"✓ Successfully processed image attachment {i}")
                        
                    except Exception as e:
                        logger.error(f"Error processing image attachment {i}: {e}")
                        processed_parts.append(f"\n--- Lỗi xử lý hình ảnh đính kèm {i}: {str(e)} ---")
            
            # Process PDF attachments
            if pdf_attachments:
                for i, pdf_attachment in enumerate(pdf_attachments, 1):
                    try:
                        logger.info(f"Processing PDF attachment {i}/{len(pdf_attachments)}")
                        
                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp_file:
                            tmp_file.write(pdf_attachment['data'])
                            tmp_file_path = tmp_file.name
                            temp_files.append(tmp_file_path)
                        
                        logger.info(f"PDF saved to temporary file: {tmp_file_path}")
                        
                        # Upload to Gemini File API
                        uploaded_file = genai.upload_file(tmp_file_path)
                        uploaded_files.append(uploaded_file)
                        logger.info(f"PDF uploaded to Gemini with URI: {uploaded_file.uri}")
                        
                        # Wait for file to be ready
                        import time
                        while uploaded_file.state.name == "PROCESSING":
                            logger.info("Waiting for PDF to be processed...")
                            time.sleep(2)
                            uploaded_file = genai.get_file(uploaded_file.name)
                        
                        # Generate summary with Gemini
                        model = genai.GenerativeModel("gemini-2.0-flash")
                        response = model.generate_content([
                            uploaded_file,
                            "Hãy tóm tắt nội dung chính của tài liệu PDF này. Trích xuất thông tin quan trọng, các điểm chính, và bất kỳ dữ liệu có giá trị nào trong tài liệu."
                        ])
                        
                        processed_parts.append(f"\n--- Tài liệu PDF đính kèm {i} ---\n{response.text}")
                        logger.info(f"✓ Successfully processed PDF attachment {i}")
                        
                    except Exception as e:
                        logger.error(f"Error processing PDF attachment {i}: {e}")
                        processed_parts.append(f"\n--- Lỗi xử lý tài liệu PDF đính kèm {i}: {str(e)} ---")
            
            # Cleanup uploaded files
            for uploaded_file in uploaded_files:
                try:
                    genai.delete_file(uploaded_file.name)
                    logger.info(f"Deleted uploaded file: {uploaded_file.name}")
                except Exception:
                    pass
            
            # Cleanup temporary files
            for tmp_file_path in temp_files:
                try:
                    os.unlink(tmp_file_path)
                    logger.info(f"Deleted temporary file: {tmp_file_path}")
                except Exception:
                    pass
            
            return "\n".join(processed_parts)
            
        except Exception as e:
            logger.error(f"Error in process_email_with_attachments: {e}")
            return f"{email_text}\n--- Lỗi xử lý đính kèm: {str(e)} ---"

    def generate_summary_and_chunks(self, existing_summary: str, processed_content: str) -> tuple[str, List[str]]:
        """
        Generate updated summary and create chunks from processed content
        
        Args:
            existing_summary: Previous summary
            processed_content: New processed content
        
        Returns:
            Tuple of (new_summary, chunks_list)
        """
        try:
            # Create summary prompt
            summary_prompt = f"""
Bạn là một chuyên gia tóm tắt email thông minh. Nhiệm vụ của bạn là cập nhật tóm tắt thread email.

## TÓM TẮT HIỆN TẠI:
{existing_summary or "Chưa có tóm tắt"}

## NỘI DUNG MỚI:
{processed_content}

## YÊU CẦU:
1. Tạo tóm tắt cập nhật cho toàn bộ thread email
2. Bao gồm thông tin từ nội dung mới và tóm tắt cũ
3. Tập trung vào:
   - Chủ đề chính và mục đích
   - Thông tin quan trọng từ text và attachments
   - Các quyết định, hành động cần thiết
   - Thông tin liên hệ quan trọng
4. Giữ tóm tắt súc tích nhưng đầy đủ (200-400 từ)

CHỈ TRẢ VỀ TÓM TẮT CUỐI CÙNG:
"""
            
            # Generate summary
            model = genai.GenerativeModel("gemini-2.0-flash")
            summary_response = model.generate_content(summary_prompt)
            new_summary = summary_response.text.strip()
            
            # Create chunks prompt
            chunks_prompt = f"""
Bạn là một chuyên gia phân tích và tổ chức nội dung email. Chia nội dung sau thành các đoạn (chunks) tối ưu cho tìm kiếm.

## NGUYÊN TẮC CHUNKING:
1. Mỗi chunk: 100-400 từ
2. Chunk phải có nghĩa hoàn chỉnh
3. Tối ưu cho semantic search
4. Bao gồm context đầy đủ

## NỘI DUNG CẦN CHIA:
{processed_content}

## OUTPUT FORMAT:
Trả về JSON với cấu trúc:
{{
  "chunks": [
    "chunk_content_1",
    "chunk_content_2",
    ...
  ]
}}

CHỈ TRẢ VỀ JSON VALID:
"""
            
            # Generate chunks
            chunks_response = model.generate_content(chunks_prompt)
            chunks_text = chunks_response.text.strip()
            
            # Clean and parse JSON
            if chunks_text.startswith("```json"):
                chunks_text = chunks_text[7:]
            if chunks_text.endswith("```"):
                chunks_text = chunks_text[:-3]
            chunks_text = chunks_text.strip()
            
            try:
                chunks_data = json.loads(chunks_text)
                chunks_list = chunks_data.get("chunks", [])
                
                if not chunks_list:
                    # Fallback: create simple chunks
                    chunks_list = [processed_content[:500]] if len(processed_content) > 500 else [processed_content]
                
                logger.info(f"Successfully created {len(chunks_list)} chunks")
                return new_summary, chunks_list
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse chunks JSON: {e}")
                # Fallback: create simple chunks
                chunks_list = [processed_content[:500]] if len(processed_content) > 500 else [processed_content]
                return new_summary, chunks_list
            
        except Exception as e:
            logger.error(f"Error in generate_summary_and_chunks: {e}")
            # Return basic fallbacks
            fallback_summary = existing_summary or "Lỗi tạo tóm tắt"
            fallback_chunks = [processed_content[:500]] if len(processed_content) > 500 else [processed_content]
            return fallback_summary, fallback_chunks 