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
import re
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
Bạn là một AI chuyên gia về xử lý ngôn ngữ, có nhiệm vụ tiền xử lý tài liệu cho hệ thống Retrieval-Augmented Generation (RAG). Mục tiêu của bạn là phân tích một tài liệu, tự động xác định các "khối nội dung" (content blocks) bên trong — đó có thể là văn bản tự do hoặc bảng dữ liệu — và áp dụng chiến lược chia khối (chunking) phù hợp nhất cho từng khối để tạo ra các chunk độc lập và giàu ngữ cảnh.

**QUY TRÌNH SUY LUẬN TỔNG QUÁT (BẮT BUỘC):**

1.  **Bước 1: Phân Đoạn Thành Các Khối Nội Dung (Content Blocks)**
    *   Quét toàn bộ tài liệu và xác định các khối nội dung riêng biệt. Một khối được định nghĩa là một cụm văn bản tự do liên tục hoặc một bảng dữ liệu hoàn chỉnh (bao gồm các dòng metadata, header, và data của nó).
    *   Xử lý từng khối một theo thứ tự xuất hiện.

2.  **Bước 2: Áp Dụng Chiến Lược Phù Hợp Cho Từng Khối**
    *   **Đối với mỗi khối, hãy tự hỏi:** "Đây là khối văn bản tự do hay khối dữ liệu dạng bảng?"
    *   Nếu là **khối văn bản tự do**, hãy áp dụng **Quy Tắc Chunking Văn Bản**.
    *   Nếu là **khối dữ liệu dạng bảng**, hãy áp dụng **Quy Tắc Chunking Dữ Liệu Bảng**.

---

### **QUY TẮC CHUNKING VĂN BẢN**
*(Áp dụng cho các khối văn bản tự do, không có cấu trúc bảng. Dựa trên hệ thống quy tắc có thứ tự ưu tiên.)*

**HỆ THỐNG QUY TẮC ƯU TIÊN (HIERARCHY OF RULES):**
Bạn PHẢI tuân thủ các quy tắc theo thứ tự ưu tiên từ cao đến thấp sau đây:

1.  **ƯU TIÊN #1 (BẮT BUỘC TUYỆT ĐỐI): RÀNG BUỘC KỸ THUẬT**
    *   Mỗi chunk **TUYỆT ĐỐI KHÔNG** được dài quá **1200 từ**.

2.  **ƯU TIÊN #2 (CỰC KỲ QUAN TRỌNG): TÍNH TOÀN VẸN NGỮ NGHĨA VÀ CẤU TRÚC**
    *   **QUY TẮC VÀNG:** Một quy trình hướng dẫn hoàn chỉnh, một luận điểm, hoặc toàn bộ thông tin cho một đối tượng cụ thể (ví dụ: "toàn bộ hướng dẫn cho sinh viên tốt nghiệp") PHẢI nằm trong **MỘT chunk duy nhất**.
    *   **Gói Gọn Ý Nghĩa:** Chunk phải là một đơn vị thông tin hoàn chỉnh.
    *   **Tôn Trọng Cấu Trúc:** KHÔNG BAO GIỜ ngắt giữa chừng một danh sách, một quy trình logic.

3.  **ƯU TIÊN #3 (KHUYẾN NGHỊ TỐI ƯU): KÍCH THƯỚC THÍCH ỨNG**
    *   **Chỉ khi đã đảm bảo Ưu tiên #2**, hãy cố gắng điều chỉnh kích thước chunk để tối ưu hiệu suất tìm kiếm:
    *   **Văn bản có cấu trúc cao (luật, hướng dẫn chi tiết):** Hướng đến chunk nhỏ hơn, khoảng **100-250 từ**.
    *   **Văn bản thông thường (bài báo, mô tả):** Hướng đến khoảng **200-400 từ**.
    *   **Văn bản tường thuật (câu chuyện):** Có thể dùng chunk lớn hơn, **350-550 từ**.

**QUY TRÌNH SUY LUẬN CHO VĂN BẢN (CHAIN-OF-THOUGHT):**
1.  **Quét Toàn Diện:** Đọc khối văn bản để nắm bắt các chủ đề và đối tượng chính.
2.  **Xác Định & Gộp Các Khối Logic:** Tìm các khối văn bản phục vụ một mục đích/đối tượng duy nhất và gộp chúng lại để tuân thủ **ƯU TIÊN #2**. Đây là các chunk chính.
3.  **Làm Giàu Ngữ Cảnh:** Với mỗi chunk, thực hiện 2 việc:
    *   Tự động **tạo một dòng tiêu đề mô tả** cho chunk.
    *   **Giải quyết tham chiếu chéo** bên trong nó bằng cách tìm và nhúng tóm tắt nội dung được tham chiếu.
4.  **Rà Soát & Tối Ưu Hóa:** Nhìn lại các chunk đã tạo, kiểm tra lại các quy tắc và điều chỉnh kích thước (nếu có thể) theo **ƯU TIÊN #3**.
5.  **Kiểm Tra Ràng Buộc Cuối Cùng:** Đảm bảo không có chunk nào vi phạm **ƯU TIÊN #1**.

---

### **QUY TẮC CHUNKING DỮ LIỆU BẢNG**
*(Áp dụng cho các khối chứa dữ liệu dạng bảng/CSV)*

1.  **Mục tiêu:** Trích xuất chính xác thông tin từ mỗi hàng, bảo toàn mối quan hệ và ngữ cảnh.
2.  **Thực thi (Chain-of-Thought cho bảng):**
    *   **a. Phân loại dòng trong khối:** Gán nhãn cho mỗi dòng là `metadata`, `table_header`, `data_row`, hoặc `blank_row`.
    *   **b. Tạo chunk:**
        *   Mỗi dòng `metadata` trở thành một chunk riêng biệt, diễn giải dưới dạng câu văn (ví dụ: "Tiêu đề: [nội dung metadata]").
        *   Bỏ qua các `blank_row`.
        *   Với mỗi `data_row`, tạo **một chunk duy nhất**. Chunk này phải là một câu văn hoàn chỉnh, diễn giải mối quan hệ dữ liệu trong hàng đó bằng cách sử dụng thông tin từ `table_header`.
        *   Nếu thiếu dữ liệu, hãy ghi nhận điều đó một cách rõ ràng.

---

**RÀNG BUỘC KỸ THUẬT CHUNG:**
*   Mỗi chunk **TUYỆT ĐỐI KHÔNG** được dài quá **1200 từ**.
*   Chỉ trả về MỘT chuỗi văn bản duy nhất. Các chunk được phân tách với nhau bởi chuỗi ký tự: `<CHUNK_SEPARATOR>`. **KHÔNG** trả về JSON hay bất kỳ định dạng nào khác.
</instructions>

<example>
### VÍ DỤ MẪU (Tài liệu kết hợp văn bản có tham chiếu chéo và bảng) ###

**Văn bản đầu vào (nội dung file .txt):**
\"\"\"
Với các bạn tốt nghiệp đợt 2023.3:
Ngày 10,11.5.25, Nhà trường trả hồ sơ tại Hội thảo C2.
Từ 12 - 22.5.2025, các bạn nhận hồ sơ tại phòng 103 - C1.
Lưu ý: Bằng và bảng điểm nhận tại Văn phòng Trường.

Với sinh viên thôi học:
Liên hệ với Ban Đào tạo để làm đơn. Sau đó, đem quyết định thôi học đến phòng 102 - C1 để đăng ký.

DANH SÁCH HỌC PHẦN THAY THẾ
Học phần học thay thế (mới),Tên HP,Học phần trong CTĐT không còn mở lớp (cũ),Tên HP
IT4651,Thiết kế và triển khai mạng IP,IT4601,Thiết bị truyền thông và mạng
\"\"\"

**Kết quả đầu ra (một chuỗi văn bản duy nhất):**
Chủ đề: Hướng dẫn nhận hồ sơ cho sinh viên tốt nghiệp đợt 2023.3.
Với các bạn tốt nghiệp đợt 2023.3:
Ngày 10,11.5.25, Nhà trường trả hồ sơ tại Hội thảo C2.
Từ 12 - 22.5.2025, các bạn nhận hồ sơ tại phòng 103 - C1.
Lưu ý: Bằng và bảng điểm nhận tại Văn phòng Trường.<CHUNK_SEPARATOR>Chủ đề: Hướng dẫn rút hồ sơ cho sinh viên thôi học.
Với sinh viên thôi học:
Liên hệ với Ban Đào tạo để làm đơn. Sau đó, đem quyết định thôi học đến phòng 102 - C1 để đăng ký.<CHUNK_SEPARATOR>Tiêu đề: DANH SÁCH HỌC PHẦN THAY THẾ<CHUNK_SEPARATOR>Học phần mới 'Thiết kế và triển khai mạng IP' (Mã: IT4651) thay thế cho học phần cũ 'Thiết bị truyền thông và mạng' (Mã: IT4601).
</example>

**ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):**
Chỉ trả về MỘT chuỗi văn bản duy nhất. Các chunk được phân tách với nhau bởi chuỗi ký tự: `<CHUNK_SEPARATOR>`. **KHÔNG** trả về JSON hay bất kỳ định dạng nào khác.
"""
            
            logger.info("Generating chunks with Gemini")
            model = genai.GenerativeModel("gemini-1.5-flash")

            generation_config = {
                "temperature": 0.2,
                "max_output_tokens": 8192,
            }

            response = model.generate_content(
                [uploaded_file, prompt],
                generation_config=generation_config
            )
            
            # Step 5: Parse response
            response_text = ""
            try:
                # The .text accessor can raise a ValueError if the response is blocked.
                response_text = response.text
            except ValueError:
                # If response.text fails, check candidate's finish_reason.
                if response.candidates and response.candidates[0].finish_reason.name != "STOP":
                    reason = response.candidates[0].finish_reason.name
                    logger.error(f"Gemini generation stopped. Reason: {reason}")
                    if reason == "MAX_TOKENS":
                        msg = "The document is too large, causing the output to exceed the model's token limit. Please try with a smaller document."
                        raise ValueError(msg)
                    elif reason == "SAFETY":
                        msg = "The content was blocked by safety settings. Please check the document content."
                        raise ValueError(msg)
                    else:
                        msg = f"Processing failed. Finish reason: {reason}"
                        raise ValueError(msg)
                # If there's no specific reason, re-raise the original error.
                raise

            logger.info(f"Received response from Gemini: {response_text[:500]}...")
            
            # Split the response text by the custom separator
            chunk_contents = response_text.split('<CHUNK_SEPARATOR>')
            
            chunks = []
            for i, content in enumerate(chunk_contents):
                # Clean up whitespace and ignore empty chunks
                cleaned_content = content.strip()
                if cleaned_content:
                    chunks.append({
                        "chunk_id": i,
                        "content": cleaned_content
                    })

            if not chunks:
                raise ValueError("No chunks created from response")
            
            logger.info(f"Successfully created {len(chunks)} chunks")
            return chunks
            
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

 