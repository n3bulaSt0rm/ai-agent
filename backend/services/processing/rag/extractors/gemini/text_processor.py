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
            
            # Step 4: Generate chunks with Gemini
            prompt = """
<instructions>
**VAI TRÒ VÀ MỤC TIÊU:**
Bạn là một AI chuyên gia về xử lý ngôn ngữ, có nhiệm vụ tiền xử lý tài liệu cho hệ thống Retrieval-Augmented Generation (RAG). Mục tiêu của bạn là chia văn bản thành các khối (chunk) độc lập, giàu ngữ nghĩa và được tối ưu cho hệ thống tìm kiếm lai (hybrid search).

**HỆ THỐNG QUY TẮC ƯU TIÊN (HIERARCHY OF RULES):**
Bạn PHẢI tuân thủ các quy tắc theo thứ tự ưu tiên từ cao đến thấp sau đây:

1.  **ƯU TIÊN #1 (BẮT BUỘC TUYỆT ĐỐI): RÀNG BUỘC KỸ THUẬT**
    *   Mỗi chunk **TUYỆT ĐỐI KHÔNG** được dài quá **1200 từ** để đảm bảo tương thích với model embedding (giới hạn 2048 tokens).

2.  **ƯU TIÊN #2 (CỰC KỲ QUAN TRỌNG): TÍNH TOÀN VẸN NGỮ NGHĨA VÀ CẤU TRÚC**
    *   **Gói Gọn Ý Nghĩa:** Mỗi chunk phải là một đơn vị thông tin hoàn chỉnh, trả lời trọn vẹn một câu hỏi hoặc mô tả đầy đủ một quy trình.
    *   **Tôn Trọng Cấu Trúc:** KHÔNG BAO GIỜ ngắt giữa chừng một danh sách, một bảng biểu, hoặc một bộ hướng dẫn logic.
    *   **QUY TẮC VÀNG:** Một quy trình hướng dẫn hoàn chỉnh cho một đối tượng cụ thể (ví dụ: "hướng dẫn cho sinh viên tốt nghiệp") PHẢI nằm trong MỘT chunk duy nhất, ngay cả khi nó dài hơn kích thước đề xuất ở Ưu tiên #3.

3.  **ƯU TIÊN #3 (KHUYẾN NGHỊ TỐI ƯU): KÍCH THƯỚC THÍCH ỨNG**
    *   Chỉ khi đã đảm bảo Ưu tiên #2, hãy cố gắng điều chỉnh kích thước chunk để tối ưu hóa hiệu suất tìm kiếm.
    *   **Văn bản có cấu trúc cao (luật, hướng dẫn):** Hướng đến chunk nhỏ hơn, khoảng **100-250 từ**.
    *   **Văn bản thông thường:** Hướng đến khoảng **200-400 từ**.
    *   **Văn bản tường thuật:** Có thể dùng chunk lớn hơn, **350-550 từ**.

**QUY TRÌNH SUY LUẬN (CHAIN-OF-THOUGHT):**
1.  **Bước 1: Quét Toàn Diện:** Đọc toàn bộ tài liệu để nắm bắt các chủ đề và đối tượng chính.
2.  **Bước 2: Xác Định Các Khối Logic:** Tìm các khối văn bản phục vụ một mục đích hoặc một đối tượng duy nhất (ví dụ: khối hướng dẫn cho sinh viên tốt nghiệp, khối hướng dẫn cho sinh viên thôi học). Đây là các chunk nháp.
3.  **Bước 3: Rà Soát và Gộp Chunk (QUAN TRỌNG):** Nhìn lại các chunk nháp. Nếu một quy trình bị chia thành nhiều chunk, hãy **GỘP CHÚNG LẠI** thành một chunk duy nhất để đảm bảo tuân thủ **ƯU TIÊN #2**.
4.  **Bước 4: Kiểm Tra Ràng Buộc Cuối Cùng:** Đảm bảo không có chunk nào vi phạm **ƯU TIÊN #1**.
5.  **Bước 5: Xuất Kết Quả:** Định dạng danh sách các chunk cuối cùng thành JSON.
</instructions>

<example>
### VÍ DỤ MẪU ###

**Văn bản đầu vào:**
"Điều 1. Về việc xét tốt nghiệp
1. Sinh viên được xét tốt nghiệp khi tích lũy đủ số tín chỉ quy định trong chương trình đào tạo và không còn nợ môn. Điểm trung bình tích lũy phải đạt từ 2.0 trở lên.
2. Ngoài ra, sinh viên phải hoàn thành các chứng chỉ Giáo dục Quốc phòng và Giáo dục Thể chất.

Điều 2. Về thủ tục
Để được công nhận tốt nghiệp, sinh viên cần nộp đơn tại Phòng Công tác sinh viên (Phòng A1) và các chứng chỉ ngoại ngữ theo yêu cầu của nhà trường trước ngày 30/06 hàng năm. Lệ phí xét tốt nghiệp là 500,000 VNĐ."

**Kết quả JSON đầu ra:**
```json
{
  "chunks": [
    {
      "chunk_id": 0,
      "content": "Điều 1. Về việc xét tốt nghiệp\n1. Sinh viên được xét tốt nghiệp khi tích lũy đủ số tín chỉ quy định trong chương trình đào tạo và không còn nợ môn. Điểm trung bình tích lũy phải đạt từ 2.0 trở lên.\n2. Ngoài ra, sinh viên phải hoàn thành các chứng chỉ Giáo dục Quốc phòng và Giáo dục Thể chất."
    },
    {
      "chunk_id": 1,
      "content": "Điều 2. Về thủ tục\nĐể được công nhận tốt nghiệp, sinh viên cần nộp đơn tại Phòng Công tác sinh viên (Phòng A1) và các chứng chỉ ngoại ngữ theo yêu cầu của nhà trường trước ngày 30/06 hàng năm. Lệ phí xét tốt nghiệp là 500,000 VNĐ."
    }
  ]
}
```
</example>

**ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):**
Chỉ trả về một đối tượng JSON hợp lệ theo cấu trúc trong ví dụ. KHÔNG thêm bất kỳ văn bản, giải thích hay định dạng markdown nào khác bên ngoài đối tượng JSON.
"""
            
            logger.info("Generating chunks with Gemini")
            model = genai.GenerativeModel("gemini-1.5-flash")

            generation_config = {
                "temperature": 0.2,
                "max_output_tokens": 8192,
                "response_mime_type": "application/json",
            }

            response = model.generate_content(
                [uploaded_file, prompt],
                generation_config=generation_config
            )
            
            # Step 5: Parse response
            # With response_mime_type="application/json", the output is a clean JSON string.
            response_text = response.text
            logger.info(f"Received response from Gemini: {response_text}...")
            
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

 