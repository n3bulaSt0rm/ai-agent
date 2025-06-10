"""
Gemini Multimodal Processor for Email Content
Processes both text content and images to create comprehensive email summaries
"""

import os
import sys
import base64
import logging
from typing import Optional, List, Dict, Any

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

from backend.core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

class GeminiMultimodalProcessor:
    """
    Processor for combining email text content with image analysis using Gemini 1.5 Flash
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the Gemini processor
        
        Args:
            api_key: Google API key (defaults to settings.GOOGLE_API_KEY)
        """
        self.api_key = api_key or settings.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key is required. Set GOOGLE_API_KEY in settings.")
            
        # Initialize Gemini model
        self.model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            api_key=self.api_key,
            temperature=0.3,
            max_tokens=2048
        )
        
        logger.info("Gemini Multimodal Processor initialized successfully")
    
    def process_email_with_images(
        self, 
        email_text: str, 
        image_attachments: List[Dict[str, Any]],
        summary_style: str = "comprehensive"
    ) -> str:
        """
        Process email text along with image attachments to create a comprehensive summary
        
        Args:
            email_text: The original email text content
            image_attachments: List of image attachment data
                Each dict should have: {'data': bytes, 'filename': str, 'mime_type': str}
            summary_style: Style of summary ("comprehensive", "brief", "structured")
            
        Returns:
            Processed email content with image analysis integrated
        """
        try:
            if not image_attachments:
                # No images, return original text without processing to save costs
                logger.info("No images found, returning original email text without Gemini processing")
                return email_text
            
            # Process images first
            logger.info(f"Processing {len(image_attachments)} images with Gemini")
            image_descriptions = self._process_images(image_attachments)
            
            # Combine text and image analysis
            return self._combine_text_and_images(email_text, image_descriptions, summary_style)
            
        except Exception as e:
            logger.error(f"Error processing email with images: {e}")
            return f"[Lỗi xử lý email: {str(e)}]\n\n{email_text}"
    

    
    def _process_images(self, image_attachments: List[Dict[str, Any]]) -> List[str]:
        """
        Process multiple images and return descriptions
        
        Args:
            image_attachments: List of image data
            
        Returns:
            List of image descriptions
        """
        descriptions = []
        
        for i, attachment in enumerate(image_attachments, 1):
            try:
                description = self._analyze_single_image(
                    attachment['data'], 
                    attachment.get('filename', f'image_{i}')
                )
                descriptions.append(description)
                
            except Exception as e:
                logger.error(f"Error processing image {attachment.get('filename', f'image_{i}')}: {e}")
                descriptions.append(f"[Không thể xử lý ảnh {attachment.get('filename', f'image_{i}')}]")
        
        return descriptions
    
    def _analyze_single_image(self, image_data: bytes, filename: str) -> str:
        """
        Analyze a single image using Gemini Vision
        
        Args:
            image_data: Raw image bytes
            filename: Name of the image file
            
        Returns:
            Description of the image content
        """
        try:
            # Convert image to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            message = HumanMessage(
                content=[
                    {
                        "type": "text", 
                        "text": """
                        Phân tích hình ảnh này và mô tả nội dung một cách chi tiết bằng tiếng Việt:

                        1. Nếu là biểu đồ/chart: Mô tả các con số, xu hướng, và insights chính
                        2. Nếu là bảng: Chuyển đổi thành text có cấu trúc rõ ràng
                        3. Nếu là văn bản: Trích xuất toàn bộ text
                        4. Nếu là hình ảnh khác: Mô tả chi tiết nội dung và ý nghĩa

                        Hãy cung cấp thông tin hữu ích và có thể hành động được.
                        """
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            )
            
            response = self.model.invoke([message])
            
            logger.info(f"Successfully analyzed image: {filename}")
            return f"📸 **Phân tích ảnh {filename}:**\n{response.content}"
            
        except Exception as e:
            logger.error(f"Error analyzing image {filename}: {e}")
            return f"[Không thể phân tích ảnh {filename}: {str(e)}]"
    
    def _combine_text_and_images(
        self, 
        email_text: str, 
        image_descriptions: List[str], 
        summary_style: str
    ) -> str:
        """
        Combine email text with image analysis using Gemini
        
        Args:
            email_text: Original email text
            image_descriptions: List of image descriptions
            summary_style: Summary style
            
        Returns:
            Combined and summarized content
        """
        try:
            # Prepare combined content
            combined_content = f"""
NỘI DUNG EMAIL:
{email_text}

THÔNG TIN TỪ HÌNH ẢNH:
{chr(10).join(image_descriptions)}
"""
            
            prompt = self._get_multimodal_processing_prompt(summary_style)
            
            messages = [
                ("system", prompt),
                ("human", combined_content)
            ]
            
            response = self.model.invoke(messages)
            return response.content
            
        except Exception as e:
            logger.error(f"Error combining text and images: {e}")
            # Fallback: return original content with image descriptions
            return f"{email_text}\n\n=== NỘI DUNG TỪ ẢNH ĐÍNH KÈM ===\n{chr(10).join(image_descriptions)}"
    

    
    def _get_multimodal_processing_prompt(self, style: str) -> str:
        """Get prompt for multimodal processing"""
        return """
        Bạn là một trợ lý AI chuyên xử lý email từ sinh viên có kèm hình ảnh.
        
        NHIỆM VỤ: Tích hợp thông tin từ văn bản và hình ảnh để tạo ra một email hoàn chỉnh từ góc độ sinh viên.
        
        YÊU CẦU CHI TIẾT:
        1. Đọc và hiểu nội dung email gốc của sinh viên
        2. Phân tích kỹ các hình ảnh đính kèm để trích xuất thông tin quan trọng
        3. Tạo ra một email mới từ góc độ sinh viên với:
           - Giữ nguyên ý định, mục đích thắc mắc ban đầu
           - Bổ sung thông tin chi tiết từ hình ảnh vào nội dung email
           - Diễn đạt thắc mắc một cách rõ ràng, cụ thể hơn
           - Cung cấp đầy đủ context cần thiết
        
        ĐỊNH DẠNG ĐẦU RA:
        - Viết email từ góc độ sinh viên xưng em
        - Bắt đầu bằng lời chào phù hợp
        - Trình bày vấn đề/thắc mắc một cách có cấu trúc
        - Tích hợp thông tin từ hình ảnh vào nội dung một cách tự nhiên
        - Kết thúc bằng lời cảm ơn và hy vọng được hỗ trợ
        
        LƯU Ý:
        - Sử dụng tiếng Việt chuẩn, lịch sự, phù hợp với văn hóa sinh viên Việt Nam
        - Không thêm thông tin không có trong email gốc và hình ảnh
        - Nếu hình ảnh chứa biểu mẫu, tài liệu -> mô tả chi tiết nội dung
        - Nếu hình ảnh là screenshot lỗi -> mô tả cụ thể lỗi gặp phải
        - Nếu hình ảnh là thông báo -> trích dẫn chính xác nội dung
        
        Hãy tạo email hoàn chỉnh, rõ ràng từ góc độ sinh viên:
        """

 