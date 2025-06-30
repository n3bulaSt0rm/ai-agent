"""
Gmail Indexing Worker using Cron Expression
"""

import logging
import time
import uuid
import tempfile
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import threading
import json
from email.utils import parsedate_to_datetime
import google.generativeai as genai

from backend.common.config import settings
from backend.adapter.sql.metadata import get_metadata_db
from backend.services.processing.rag.extractors.gemini.gemini_email_processor import GeminiEmailProcessor
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.services.processing.rag.common.qdrant import ChunkData
from backend.services.processing.rag.common.utils import (
    extract_text_content, extract_all_attachments, 
    run_cron_scheduler
)

logger = logging.getLogger(__name__)

class GmailIndexingWorker:
    """Gmail indexing worker using cron expression for scheduling"""
    
    def __init__(self, 
                 gmail_service,  
                 user_id: str,
                 gemini_processor: Optional[GeminiEmailProcessor] = None,
                 embedding_module: Optional[VietnameseEmbeddingModule] = None):  
        self.gmail_service = gmail_service
        self.user_id = user_id
        
        self.cron_expression = settings.WORKER_CRON_EXPRESSION
        self.collection_name = settings.EMAIL_QA_COLLECTION
        
        self.metadata_db = get_metadata_db()
        
        self.gemini_email_processor = gemini_processor
        self.embedding_module = embedding_module
        
        self.is_running = False
        self.is_scheduled = False
        self.worker_thread = None
        
        # Configure Gemini if API key is available
        if settings.GOOGLE_API_KEY:
            genai.configure(api_key=settings.GOOGLE_API_KEY)
        
        logger.info(f"Indexing Worker initialized - Cron: {self.cron_expression}")
    

    
    def _filter_new_messages(self, messages: List[Dict], last_processed_message_id: str = None) -> List[Dict]:
        """Filter messages to get only new ones after the last processed message"""
        if not last_processed_message_id:
            return messages
        
        filtered_messages = []
        found_last = False
        
        for message in messages:
            if message['id'] == last_processed_message_id:
                found_last = True
                continue
            if found_last:
                filtered_messages.append(message)
        
        if not found_last:
            logger.warning(f"Last processed message {last_processed_message_id} not found, processing all messages")
            return messages
        
        return filtered_messages

    def _process_email_content(self, message: Dict) -> Optional[Dict[str, Any]]:
        """Process a single email message and extract content and attachments"""
        try:
            payload = message['payload']
            headers = {h['name']: h['value'] for h in payload['headers']}
            
            text_content = extract_text_content(payload)
            
            # Extract all attachments
            all_attachments = extract_all_attachments(
                self.gmail_service, self.user_id, payload, message['id']
            )
            
            # Separate attachments by type for easier processing
            image_attachments = [att for att in all_attachments if att.get('attachment_type') == 'image']
            pdf_attachments = [att for att in all_attachments if att.get('attachment_type') == 'pdf']
            
            return {
                'id': message['id'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'text_content': text_content,
                'image_attachments': image_attachments,
                'pdf_attachments': pdf_attachments
            }
            
        except Exception as e:
            logger.error(f"Error processing message {message.get('id')}: {e}")
            return None
    
    def _get_new_messages(self, thread_id: str, last_processed_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get new messages from thread since last processed - using clean logic from handler"""
        try:
            # Fetch thread messages
            thread_messages = self.gmail_service.users().threads().get(
                userId=self.user_id,
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread_messages.get('messages', [])
            if not messages:
                return []
            
            # Filter to get only new messages
            filtered_messages = self._filter_new_messages(messages, last_processed_id)
            if not filtered_messages:
                logger.info(f"No new messages to process for thread {thread_id}")
                return []
            
            # Process each message
            new_messages = []
            for message in filtered_messages:
                processed_email = self._process_email_content(message)
                if processed_email:
                    new_messages.append(processed_email)
            
            logger.info(f"Processed {len(new_messages)} new messages from thread {thread_id}")
            return new_messages
            
        except Exception as e:
            logger.error(f"Error getting messages for thread {thread_id}: {e}")
            return []
    
    def _create_gemini_conversation(self) -> Optional[Any]:
        """Create a Gemini conversation for processing emails"""
        try:
            system_instruction = f"""
# VAI TRÒ VÀ MỤC TIÊU
Bạn là một Trợ lý AI chuyên nghiệp của Phòng Công tác Sinh viên, có nhiệm vụ phân tích các luồng email từ sinh viên một cách chính xác, khách quan và hiệu quả để tạo ra tri thức có thể tái sử dụng cho hệ thống RAG.

# CÁC NGUYÊN TẮC HOẠT ĐỘNG BẮT BUỘC
Bạn PHẢI tuân thủ nghiêm ngặt các nguyên tắc sau trong mọi phản hồi:

1.  **Objectivity:** Chỉ phân tích và trích xuất thông tin dựa trên dữ liệu được cung cấp trong email. Tuyệt đối không suy diễn, không thêm thông tin không có.
2.  **Precision:** Đảm bảo mọi thông tin được tóm tắt hoặc trích xuất đều chính xác tuyệt đối so với email gốc.
3.  **Knowledge-Focus:** Tập trung vào việc trích xuất và tổng hợp tri thức từ các email phản hồi của {settings.GMAIL_EMAIL_ADDRESS}.

# NĂNG LỰC CỐT LÕI
Bạn có khả năng hiểu sâu sắc ngữ cảnh email, phân biệt người gửi/nhận, và trích xuất tri thức hữu ích từ các câu trả lời của phòng CTSV.

Hãy sẵn sàng xử lý các yêu cầu phân tích email và tạo tri thức.
"""
            
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=system_instruction,
                generation_config={
                    "max_output_tokens": 8192,
                    "temperature": 0.3
                }
            )
            chat = model.start_chat(history=[])
            
            return chat
            
        except Exception as e:
            logger.error(f"Error creating Gemini conversation: {e}")
            return None

    def _create_summary_update_prompt(self, thread_content: str, existing_summary: str) -> str:
        """Creates a prompt to update summary from emails"""
        return f"""
# VAI TRÒ VÀ MỤC TIÊU
Bạn là một Trợ lý AI chuyên nghiệp của Phòng Công tác Sinh viên, có nhiệm vụ phân tích các luồng email từ sinh viên một cách chính xác, khách quan và hiệu quả để tạo ra tri thức có thể tái sử dụng cho hệ thống RAG.

# NHIỆM VỤ: CẬP NHẬT TÓM TẮT
Phân tích các email mới dưới đây và tích hợp chúng vào bối cảnh chung một cách chính xác. Trọng tâm của bạn là các câu hỏi và yêu cầu tường minh trong **nội dung email**. Các **file đính kèm (hình ảnh, PDF) chỉ đóng vai trò là bằng chứng hoặc thông tin bổ sung** cho các yêu cầu đó và **TUYỆT ĐỐI KHÔNG** được dùng để tự tạo ra câu hỏi mới.

**TÓM TẮT BỐI CẢNH HIỆN TẠI:**
(Lưu ý: Bối cảnh này có thể chứa 2 phần, được ngăn cách bởi '|||'. Phần đầu là tóm tắt hội thoại, phần sau là tóm tắt tri thức.)
---
{existing_summary}
---

**CÁC EMAIL MỚI CẦN PHÂN TÍCH:**
(Lưu ý: Các file đính kèm được cung cấp riêng và chỉ mang tính bổ trợ cho nội dung email)
---
{thread_content}
---

# QUY TRÌNH SUY LUẬN VÀ THỰC HIỆN (BẮT BUỘC)
1.  **Phân tích Email Mới:** Đọc kỹ từng email mới. Xác định người gửi và nội dung chính họ muốn truyền đạt.
2.  **Cập nhật Tóm tắt (2 Phần):**
    -   **Phần 1 - Tóm tắt cuộc hội thoại:** Dựa vào tóm tắt hội thoại cũ (nếu có, là phần trước dấu ngăn cách trong bối cảnh hiện tại) và email mới, tạo một bản tóm tắt **HOÀN TOÀN MỚI** cho **toàn bộ cuộc hội thoại**.
    -   **Phần 2 - Tóm tắt tri thức:** Dựa trên **toàn bộ luồng email**, hãy **chắt lọc và tổng hợp lại các thông tin hữu ích có thể tái sử dụng** được cung cấp trong các email phản hồi từ tài khoản `{settings.GMAIL_EMAIL_ADDRESS}`. Đây là phần CỰC KỲ QUAN TRỌNG, dùng để chunking cho RAG.
        - **Nguồn tri thức chính:** Nội dung trong các email được gửi **TỪ** `{settings.GMAIL_EMAIL_ADDRESS}` (ví dụ: các câu trả lời, hướng dẫn quy trình, thông báo, yêu cầu bổ sung giấy tờ...).
        - **Bối cảnh:** Sử dụng nội dung email của sinh viên (người hỏi) để làm rõ bối cảnh cho câu trả lời của phòng CTSV.
        - **Yêu cầu:** Bản tóm tắt tri thức phải chi tiết, đầy đủ, khách quan và **TUYỆT ĐỐI KHÔNG** chứa thông tin định danh cá nhân (tên, MSSV), lời chào hỏi, hoặc các câu trao đổi không mang tính tri thức. Hãy tích hợp thông tin quan trọng từ file đính kèm vào phần này khi phù hợp.

# VÍ DỤ CỤ THỂ
---
**Input (Tóm tắt bối cảnh hiện tại):**
"Sinh viên hỏi về thủ tục xin học bổng XYZ ||| Thông tin cần xử lý: thủ tục và giấy tờ cần thiết cho học bổng XYZ."

**Input (Email mới + file đính kèm là ảnh 'Giấy chứng nhận hộ nghèo'):**
"Dạ em chào phòng CTSV, em đã chuẩn bị xong hồ sơ như hướng dẫn ạ. Em gửi file PDF đơn và giấy chứng nhận hộ nghèo. Nhờ phòng kiểm tra giúp em xem đã đủ chưa ạ?"

**Output (JSON):**
```json
{{
  "updated_summary": "Sinh viên hỏi về thủ tục xin học bổng XYZ và đã nộp đơn cùng giấy chứng nhận hộ nghèo, muốn xác nhận hồ sơ đã đủ chưa ||| Thông tin cần xử lý: thủ tục và giấy tờ cần thiết cho học bổng XYZ, bao gồm đơn và giấy chứng nhận hộ nghèo. Cần xác định danh sách đầy đủ các giấy tờ."
}}
```
---

# YÊU CẦU ĐẦU RA
Trả về tóm tắt đã cập nhật với 2 phần được ngăn cách bởi '|||'.

# QUY TẮC RÀNG BUỘC
-   Tóm tắt phải khách quan, dựa trên thông tin có trong email và file đính kèm.
-   Sử dụng thông tin trong file đính kèm để làm giàu ngữ cảnh và cung cấp thêm chi tiết cho tóm tắt.
-   **QUAN TRỌNG:** Thông tin phải xuất phát từ nội dung email. **TUYỆT ĐỐI KHÔNG** tự tạo thông tin chỉ dựa vào nội dung file đính kèm.
-   Luôn trả về cả 2 phần tóm tắt, ngay cả khi một trong hai phần trống.
"""

    def _create_chunks_extraction_prompt(self, knowledge_summary: str) -> str:
        """Creates a prompt to extract chunks from knowledge summary"""
        return f"""Bạn là AI chuyên gia xử lý tài liệu cho hệ thống RAG. Nhiệm vụ của bạn là phân tích nội dung email và tạo ra các chunk tri thức độc lập, giàu ngữ cảnh.

**NỘI DUNG EMAIL CẦN CHUNKING:**
---
{knowledge_summary}
---

**HỆ THỐNG QUY TẮC ƯU TIÊN (BẮT BUỘC TUÂN THỦ):**

**1. ƯU TIÊN #1 - TÍNH TOÀN VẸN NGỮ NGHĨA (CỰC KỲ QUAN TRỌNG):**
- **QUY TẮC VÀNG:** Một chủ đề/vấn đề hoàn chỉnh (ví dụ: toàn bộ quy trình, tất cả yêu cầu cho một thủ tục) PHẢI nằm trong MỘT chunk duy nhất.
- **Độc lập:** Người đọc phải hiểu được chunk mà không cần xem các chunk khác.

**2. ƯU TIÊN #2 - KÍCH THƯỚC TỐI ƯU (CHO EMAIL):**
- **Ràng buộc:** Tối đa 150 từ.
- **Mục tiêu:** Hướng đến 50-120 từ.
- Luôn ưu tiên **TÍNH TOÀN VẸN** hơn là đạt được kích thước mục tiêu.

**QUY TRÌNH SUY LUẬN (CHAIN-OF-THOUGHT):**
1.  **Quét toàn diện:** Đọc kỹ toàn bộ nội dung email để nắm bắt các chủ đề, câu hỏi, và các hướng dẫn được cung cấp.
2.  **Xác định & Gộp Khối Logic:**
    -   Tìm các khối thông tin phục vụ một mục đích duy nhất (ví dụ: các bước của một quy trình, danh sách các giấy tờ cần thiết, thông tin về thời hạn).
    -   Gộp các câu liên quan chặt chẽ để tạo thành một chunk hoàn chỉnh, tuân thủ **QUY TẮC VÀNG**.
3.  **Làm giàu & Hoàn thiện Ngữ cảnh:**
    -   Với mỗi chunk, hãy đảm bảo nó chứa đủ thông tin để có thể hiểu độc lập. Nếu chunk nói về "hạn chót", phải làm rõ đó là "hạn chót của việc gì".
    -   Loại bỏ hoàn toàn thông tin cá nhân (tên, MSSV), lời chào hỏi, cảm ơn.
4.  **Tạo Tiêu đề & Kiểm tra:**
    -   Tạo một tiêu đề mô tả ngắn gọn cho mỗi chunk.
    -   Kiểm tra lại lần cuối để đảm bảo mọi quy tắc đều được tuân thủ.

**ĐỊNH DẠNG ĐẦU RA (Mỗi chunk trên một dòng riêng):**
[Chủ đề]: Nội dung chi tiết...

**VÍ DỤ CỤ THỂ:**
[Hồ sơ học bổng ABC]: Để đăng ký học bổng ABC, sinh viên cần hoàn thành đơn đăng ký trực tuyến và nộp bản cứng giấy chứng nhận gia đình có hoàn cảnh khó khăn tại phòng C1-102.
[Thời hạn học bổng ABC]: Hạn cuối nộp hồ sơ cho học bổng ABC là ngày 25 tháng 12 năm 2024.
[Thông báo kết quả học bổng ABC]: Kết quả xét duyệt học bổng ABC sẽ được gửi qua email cho sinh viên sau 2 tuần kể từ hạn chót nộp hồ sơ.

Nếu không có thông tin tri thức, trả về: **NO_CHUNKS**
"""

    def _update_summary_with_gemini(self, conversation: Any, existing_summary: str, new_messages: List[Dict[str, Any]]) -> tuple[str, List[Tuple[Any, str]]]:
        """Step 1: Update summary from emails using Gemini"""
        uploaded_files_to_clean = []
        try:
            logger.info(f"Step 1: Updating summary from {len(new_messages)} new messages")
            
            # Build thread content and upload attachments
            prompt_parts = []
            thread_text = ""
            
            # Process each message
            for i, msg in enumerate(new_messages, 1):
                email_text = f"""
=== EMAIL {i} ===
Từ: {msg['from']}
Đến: {msg.get('to', '')}
Tiêu đề: {msg['subject']}
Ngày: {msg['date']}
Nội dung: {msg['text_content']}
"""
                
                # Handle attachments - combine image and pdf attachments into single list
                all_attachments = msg.get('image_attachments', []) + msg.get('pdf_attachments', [])
                if all_attachments:
                    email_text += "\n--- File đính kèm ---\n"
                    for att in all_attachments:
                        email_text += f"- {att.get('filename', 'N/A')}\n"
                
                thread_text += email_text + "\n"
                
                # Upload attachments to Gemini
                for attachment in all_attachments:
                    mime_type = attachment.get('mime_type')
                    data = attachment.get('data')
                    filename = attachment.get('filename', 'attachment')

                    if not mime_type or not data:
                        continue

                    if mime_type.startswith('image/') or mime_type == 'application/pdf':
                        try:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                                temp_file.write(data)
                                temp_path = temp_file.name
                            
                            uploaded_file = genai.upload_file(temp_path, mime_type=mime_type, display_name=filename)
                            
                            # Wait for processing
                            while uploaded_file.state.name == "PROCESSING":
                                time.sleep(1)
                                uploaded_file = genai.get_file(uploaded_file.name)
                            
                            if uploaded_file.state.name == "ACTIVE":
                                prompt_parts.append(uploaded_file)
                                uploaded_files_to_clean.append((uploaded_file, temp_path))
                                logger.debug(f"✓ Uploaded attachment: {filename}")
                            else:
                                os.unlink(temp_path)
                                logger.warning(f"Failed to upload attachment: {filename}")
                                        
                        except Exception as upload_error:
                            logger.error(f"Error uploading attachment {filename}: {upload_error}")
                            if 'temp_path' in locals():
                                try:
                                    os.unlink(temp_path)
                                except:
                                    pass

            # Create summary update prompt
            summary_prompt = self._create_summary_update_prompt(thread_text, existing_summary)
            full_prompt = [summary_prompt] + prompt_parts
            
            try:
                response = conversation.send_message(
                    full_prompt,
                    generation_config={
                        "max_output_tokens": 8192,
                        "temperature": 0.3, 
                        "response_mime_type": "application/json",
                        "response_schema": {
                            "type": "object",
                            "properties": {
                                "updated_summary": {
                                    "type": "string",
                                    "description": "Tóm tắt đã cập nhật với 2 phần ngăn cách bởi |||"
                                }
                            },
                            "required": ["updated_summary"]
                        }
                    }
                )
                
                # Parse JSON response
                try:
                    data = json.loads(response.text.strip())
                    updated_summary = data.get("updated_summary", "")
                    
                    logger.info(f"✓ Step 1 completed: Updated summary")
                    return updated_summary, uploaded_files_to_clean
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from Gemini response: {e}\n---\n{response.text}\n---")
                    return existing_summary, uploaded_files_to_clean
                    
            except Exception as e:
                logger.error(f"Error calling Gemini API for summary update: {e}")
                return existing_summary, uploaded_files_to_clean
                    
        except Exception as e:
            logger.error(f"Error updating summary with Gemini: {e}")
            return existing_summary, uploaded_files_to_clean

    def _extract_chunks_from_knowledge(self, conversation: Any, updated_summary: str) -> List[str]:
        """Step 2: Extract chunks from knowledge summary using Gemini"""
        try:
            logger.info("Step 2: Extracting chunks from knowledge summary")
            
            # Extract knowledge part (part 2) from summary
            if "|||" in updated_summary:
                parts = updated_summary.split("|||", 1)
                knowledge_summary = parts[1].strip() if len(parts) > 1 else ""
            else:
                knowledge_summary = updated_summary
            
            if not knowledge_summary:
                logger.info("No knowledge summary found, returning empty chunks")
                return []
            
            # Create chunks extraction prompt
            chunks_prompt = self._create_chunks_extraction_prompt(knowledge_summary)
            
            try:
                response = conversation.send_message(
                    chunks_prompt,
                    generation_config={
                        "max_output_tokens": 8192,
                        "temperature": 0.3
                    }
                )
                
                # Parse simple line-by-line format
                try:
                    response_text = response.text.strip()
                    
                    # Check for NO_CHUNKS case
                    if response_text == "NO_CHUNKS":
                        logger.info("✓ Step 2 completed: No chunks to extract")
                        return []
                    
                    # Split by newlines and filter non-empty lines
                    chunks = [line.strip() for line in response_text.split('\n') if line.strip()]
                    
                    logger.info(f"✓ Step 2 completed: Extracted {len(chunks)} chunks")
                    return chunks
                    
                except Exception as e:
                    logger.error(f"Failed to parse line-by-line response: {e}\n---\n{response.text}\n---")
                    return []
                    
            except Exception as e:
                logger.error(f"Error calling Gemini API for chunks extraction: {e}")
                return []
                    
        except Exception as e:
            logger.error(f"Error extracting chunks from knowledge: {e}")
            return []

    def _process_with_gemini(self, existing_summary: str, new_messages: List[Dict[str, Any]]) -> tuple[str, List[str]]:
        """Process messages with Gemini in 2 steps: 1) Update summary, 2) Extract chunks"""
        uploaded_files_to_clean = []
        try:
            if not new_messages:
                return existing_summary, []
            
            logger.info(f"Processing {len(new_messages)} new messages with Gemini (2-step process)")
            
            # Create Gemini conversation for context sharing
            conversation = self._create_gemini_conversation()
            if not conversation:
                logger.error("Failed to create Gemini conversation")
                return existing_summary, []
            
            # Step 1: Update summary
            updated_summary, uploaded_files_to_clean = self._update_summary_with_gemini(
                conversation, existing_summary, new_messages
            )
            
            # Step 2: Extract chunks from knowledge summary
            chunks = self._extract_chunks_from_knowledge(conversation, updated_summary)
            
            logger.info(f"✓ 2-step process completed: Updated summary + {len(chunks)} chunks")
            return updated_summary, chunks
            
        except Exception as e:
            logger.error(f"Error in 2-step Gemini processing: {e}")
            return existing_summary, []
        finally:
            # Cleanup uploaded files
            if uploaded_files_to_clean:
                logger.debug(f"Cleaning up {len(uploaded_files_to_clean)} uploaded files")
                for uploaded_file, temp_path in uploaded_files_to_clean:
                    try:
                        genai.delete_file(uploaded_file.name)
                        os.unlink(temp_path)
                    except Exception as e:
                        logger.warning(f"Failed to clean up file {uploaded_file.name if uploaded_file else 'N/A'} or temp path {temp_path}: {e}")
    
    def _delete_chunks_with_collection_switch(self, embedding_id: str) -> bool:
        """Delete chunks with collection switching for EMAIL_QA_COLLECTION"""
        try:
            original_collection = self.embedding_module.qdrant_manager.collection_name
            try:
                self.embedding_module.qdrant_manager.collection_name = settings.EMAIL_QA_COLLECTION
                return self.embedding_module.qdrant_manager.delete_chunks_by_file_id(embedding_id)
            except Exception as e:
                logger.error(f"Error deleting chunks for embedding_id {embedding_id}: {e}")
                return False
            finally:
                self.embedding_module.qdrant_manager.collection_name = original_collection
        except Exception as e:
            logger.error(f"Error in collection switching for embedding_id {embedding_id}: {e}")
            return False

    def _embed_chunks(self, chunks: List[str], embedding_id: str, file_created_at: str, thread_id: str = None) -> bool:
        """Embed chunks to Qdrant with collection switching for EMAIL_QA_COLLECTION"""
        try:
            if not chunks:
                return True
            
            original_collection = self.embedding_module.qdrant_manager.collection_name
            try:
                self.embedding_module.qdrant_manager.collection_name = settings.EMAIL_QA_COLLECTION
                
                chunk_data_list = []
                for i, content in enumerate(chunks):
                    chunk_data_list.append(ChunkData(
                        chunk_id=i + 1,
                        content=content,
                        file_id=embedding_id,
                        file_created_at=file_created_at or datetime.now().isoformat(),
                        parent_chunk_id=0,
                        source="gmail_thread"
                    ))
                
                self.embedding_module.index_documents(chunk_data_list)
                logger.info(f"✓ Embedded {len(chunks)} chunks")
                return True
                
            except Exception as e:
                logger.error(f"Error embedding chunks: {e}")
                return False
            finally:
                self.embedding_module.qdrant_manager.collection_name = original_collection
            
        except Exception as e:
            logger.error(f"Error in collection switching for embedding: {e}")
            return False
    
    def _get_threads_to_process(self) -> List[Dict[str, Any]]:
        """Get threads that need processing - only non-outdated threads"""
        try:
            return self.metadata_db.get_threads_to_process()
        except Exception as e:
            logger.error(f"Error getting threads to process: {e}")
            return []
    
    def _process_single_thread(self, thread_record: Dict[str, Any]) -> bool:
        thread_id = thread_record['thread_id']
        existing_summary = thread_record.get('context_summary', '')
        last_processed_id = thread_record.get('last_processed_message_id')
        old_embedding_id = thread_record.get('embedding_id')  
        
        try:
            new_messages = self._get_new_messages(thread_id, last_processed_id)
            if not new_messages:
                return True
            
            new_summary, chunks = self._process_with_gemini(existing_summary, new_messages)
            
            new_last_processed_id = new_messages[-1]['id']
            new_embedding_id = thread_id + "," + new_last_processed_id
            
            try:
                latest_email_date = new_messages[-1]['date']
                if latest_email_date:
                    try:
                        parsed_date = parsedate_to_datetime(latest_email_date)
                        if parsed_date:
                            latest_email_date = parsed_date.isoformat()
                        else:
                            logger.warning(f"Failed to parse email date: {latest_email_date}")
                            latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
                    except Exception as date_error:
                        logger.error(f"Error parsing email date '{latest_email_date}': {date_error}")
                        latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
                else:
                    latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
            except Exception as e:
                logger.error(f"Error getting email date for thread {thread_id}: {e}")
                latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
            
            # Embed new chunks first
            if not self._embed_chunks(chunks, new_embedding_id, latest_email_date, thread_id):
                logger.error(f"Failed to embed new chunks for thread {thread_id}")
                return False
            
            # Update metadata in database
            success = self.metadata_db.upsert_gmail_thread(
                thread_id=thread_id,
                context_summary=new_summary,
                last_processed_message_id=new_last_processed_id,
                embedding_id=new_embedding_id
            )
            
            if not success:
                logger.error(f"Failed to update metadata for thread {thread_id}")
                self._delete_chunks_with_collection_switch(new_embedding_id)
                return False
            
            # Delete old chunks after successful metadata update
            if old_embedding_id and old_embedding_id != new_embedding_id:
                self._delete_chunks_with_collection_switch(old_embedding_id)
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing thread {thread_id}: {e}")
            return False
    
    def _run_processing(self):
        """Run the main processing loop"""
        if self.is_running:
            logger.warning("Processing already running")
            return
        
        self.is_running = True
        logger.info("Starting thread processing")
        
        try:
            # Initialize components if needed
            if not self.gemini_email_processor:
                self.gemini_email_processor = GeminiEmailProcessor()
            
            if not self.embedding_module:
                from backend.services.processing.rag.common.utils import initialize_embedding_module
                self.embedding_module = initialize_embedding_module(settings.EMAIL_QA_COLLECTION)
                if not self.embedding_module:
                    logger.error("Failed to initialize embedding module")
                    return
            
            threads = self._get_threads_to_process()
            if not threads:
                logger.info("No threads to process")
                return
            
            logger.info(f"Processing {len(threads)} threads")
            
            processed = 0
            for thread_record in threads:
                if not self.is_running:
                    break
                
                thread_id = thread_record.get('thread_id', 'unknown')
                
                if self._process_single_thread(thread_record):
                    processed += 1
                else:
                    logger.error(f"Failed to process thread {thread_id}")
                
                time.sleep(5) 
            
            logger.info(f"Processing complete: {processed}/{len(threads)}")
            
        except Exception as e:
            logger.error(f"Error in processing: {e}")
        finally:
            self.is_running = False
    
    def _scheduler_loop(self):
        """Run the cron scheduler loop"""
        run_cron_scheduler(
            self.cron_expression,
            self._run_processing,
            "Gmail Indexing Worker",
            None
        )
    
    def start(self):
        """Start the indexing worker"""
        if self.worker_thread and self.worker_thread.is_alive():
            logger.warning("Worker already running")
            return
        
        self.is_scheduled = True
        self.worker_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Indexing worker started")
    
    def stop(self):
        """Stop the worker"""
        self.is_running = False
        self.is_scheduled = False
        logger.info("Indexing worker stopped")
    
    def run_once(self):
        """Run processing once"""
        logger.info("Running indexing once...")
        self._run_processing()

 