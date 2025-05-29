"""
Gemini Model for RAG Pipeline
"""

import logging
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from base_model import BaseModel

logger = logging.getLogger(__name__)

class GeminiModel(BaseModel):
    """Gemini model for generating answers."""
    
    def generate_answer(self, query: str, context: str) -> str:
        """
        Generate an answer using Gemini API.
        
        Args:
            query (str): The question
            context (str): The context
            
        Returns:
            str: The generated answer
        """
        try:
            import google.generativeai as genai
            
            # Configure API
            genai.configure(api_key=self.api_key)
            
            # Get model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens
                }
            )
            
            # Create prompt
            prompt = f"""Sử dụng thông tin trong ngữ cảnh sau để trả lời câu hỏi. Chỉ sử dụng thông tin từ ngữ cảnh và trả lời bằng tiếng Việt. Nếu không có thông tin để trả lời, hãy nói là bạn không tìm thấy thông tin liên quan.
            
Ngữ cảnh:
{context}

Câu hỏi: {query}

Trả lời:"""
            
            # Generate answer
            response = model.generate_content(prompt)
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating answer with Gemini: {e}")
            return f"Lỗi khi tạo câu trả lời: {str(e)}"
