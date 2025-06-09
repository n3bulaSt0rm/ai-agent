"""
OpenAI Model for RAG Pipeline
"""

import logging

from backend.services.processing.rag.models.base_model import BaseModel

logger = logging.getLogger(__name__)

class OpenAIModel(BaseModel):
    """OpenAI model for generating answers."""
    
    def generate_answer(self, query: str, context: str) -> str:
        """
        Generate an answer using OpenAI API.
        
        Args:
            query (str): The question
            context (str): The context
            
        Returns:
            str: The generated answer
        """
        try:
            import openai
            openai.api_key = self.api_key
            
            # Create prompt with system message and context
            messages = [
                {"role": "system", "content": "Bạn là trợ lý AI trả lời các câu hỏi dựa trên thông tin được cung cấp. Chỉ sử dụng thông tin từ ngữ cảnh được cung cấp và trả lời bằng tiếng Việt. Nếu không có thông tin để trả lời, hãy nói là bạn không tìm thấy thông tin liên quan."},
                {"role": "user", "content": f"Ngữ cảnh:\n{context}\n\nCâu hỏi: {query}"}
            ]
            
            # Call API
            response = openai.ChatCompletion.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            # Extract and return answer
            answer = response.choices[0].message.content
            return answer
            
        except Exception as e:
            logger.error(f"Error generating answer with OpenAI: {e}")
            return f"Lỗi khi tạo câu trả lời: {str(e)}" 