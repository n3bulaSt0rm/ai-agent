"""
DeepSeek Model for RAG Pipeline
"""

import logging
import requests
import os

# Import from the central config
from backend.core.config import settings
from backend.services.processing.rag.models.base_model import BaseModel

logger = logging.getLogger(__name__)

class DeepSeekModel(BaseModel):
    """DeepSeek model for generating answers."""
    
    def generate_answer(self, query: str, context: str) -> str:
        """
        Generate an answer using DeepSeek API.
        
        Args:
            query (str): The question
            context (str): The context
            
        Returns:
            str: The generated answer
        """
        try:
            # Construct prompt for DeepSeek
            prompt = f"""Sử dụng thông tin trong ngữ cảnh sau để trả lời câu hỏi. Chỉ sử dụng thông tin từ ngữ cảnh và trả lời bằng tiếng Việt. Nếu không có thông tin để trả lời, hãy nói là bạn không tìm thấy thông tin liên quan.
            
Ngữ cảnh:
{context}

Câu hỏi: {query}

Trả lời:"""
            
            # API endpoint from settings
            url = settings.DEEPSEEK_API_URL
            
            # Request headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Request data
            data = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            
            # Make API request
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                answer = response.json()["choices"][0]["message"]["content"]
                return answer
            else:
                error_msg = f"API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return f"Lỗi khi tạo câu trả lời: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error generating answer with DeepSeek: {e}")
            return f"Lỗi khi tạo câu trả lời: {str(e)}"
