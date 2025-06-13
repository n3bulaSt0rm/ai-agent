import os
import base64
import json
import asyncio
import logging
import time
import google.generativeai as genai

from datetime import datetime, time as datetime_time
from typing import Dict, Any, List, Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.services.processing.rag.retrievers.qdrant_retriever import VietnameseQueryModule, create_query_module
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.core.config import settings
from backend.db.metadata import get_metadata_db

from backend.services.processing.rag.draft_monitor import EmailDraftMonitor

from backend.services.processing.rag.utils import (
    create_deepseek_client, DeepSeekAPIClient, 
    extract_image_attachments, extract_text_content, extract_all_attachments
)

from backend.services.processing.rag.extractors.gemini.gemini_email_processor import GeminiEmailProcessor
from backend.services.processing.rag.gmail_api_monitor import create_gmail_api_monitor
from backend.services.processing.rag.gmail_indexing_worker import GmailIndexingWorker
from backend.services.processing.rag.gmail_cleanup_worker import GmailCleanupWorker

logger = logging.getLogger(__name__)

class GmailHandler:
    """
    Gmail handler that processes emails with multimodal content using Gemini
    """
    
    def __init__(self, token_path: str = None):
        """
        Initialize Gmail handler with Gemini always enabled.
        
        Args:
            token_path: Path to the token JSON file  
        """
        self.token_path = token_path or settings.GMAIL_TOKEN_PATH
        self.service = None
        self.user_id = 'me'
        
        try:
            if settings.GOOGLE_API_KEY:
                genai.configure(api_key=settings.GOOGLE_API_KEY)
                logger.debug("Gemini API configured")
            
            self.gemini_processor = GeminiEmailProcessor()
            logger.debug("Gemini email processor initialized")
        except Exception as e:
            logger.error(f"Gemini initialization failed: {e}")
            raise Exception(f"Required Gemini processor failed to initialize: {e}")
        
        self.deepseek_api_key = settings.DEEPSEEK_API_KEY
        self.deepseek_api_url = settings.DEEPSEEK_API_URL
        self.deepseek_model = settings.DEEPSEEK_MODEL
        
        self.deepseek_client = create_deepseek_client(
            deepseek_api_key=self.deepseek_api_key,
            deepseek_api_url=self.deepseek_api_url,
            deepseek_model=self.deepseek_model
        )
        
        self.query_module = None
        
        self.metadata_db = get_metadata_db()
        
        self.draft_monitor = None
        self.api_monitor = None
        
        self.background_worker = None
        self.cleanup_worker = None
        
        if not self.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY not set in settings")
    
    def _initialize_managers(self):
        """Initialize draft monitor and API monitor after authentication."""
        if not self.service:
            logger.error("Gmail service not authenticated, cannot initialize managers")
            return
        
        self.draft_monitor = EmailDraftMonitor(
            service=self.service,
            metadata_db=self.metadata_db,
            user_id=self.user_id
        )
        
        self.api_monitor = create_gmail_api_monitor(gmail_handler=self, poll_interval=settings.GMAIL_POLL_INTERVAL)
        
        logger.info("Draft monitor and Gmail API monitor initialized successfully")

    def _init_indexing_worker(self):
        """Initialize indexing worker (called separately after authentication)"""
        if not self.service:
            logger.error("Gmail service not authenticated, cannot initialize indexing worker")
            return False
        
        try:
            if self.query_module is None:
                self._init_query_module()
            
            embedding_module = None
            if hasattr(self.query_module, 'embedding_module'):
                embedding_module = self.query_module.embedding_module
                logger.info("Using shared embedding module from query module")
            
            self.background_worker = GmailIndexingWorker(
                gmail_service=self.service,
                user_id=self.user_id,
                gemini_processor=self.gemini_processor,
                embedding_module=embedding_module
            )
            self.background_worker.start()
            logger.info("Gmail indexing worker initialized and started")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize indexing worker: {e}")
            return False

    def _init_cleanup_worker(self):
        """Initialize cleanup worker for outdated threads"""
        try:
            # Initialize query module first to get embedding module
            if self.query_module is None:
                self._init_query_module()
            
            # Get embedding module from query module
            embedding_module = None
            if hasattr(self.query_module, 'embedding_module'):
                embedding_module = self.query_module.embedding_module
                logger.info("Using shared embedding module from query module")
            
            self.cleanup_worker = GmailCleanupWorker(embedding_module=embedding_module)
            self.cleanup_worker.start()
            logger.info("Gmail cleanup worker initialized and started")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize cleanup worker: {e}")
            return False

    def _init_query_module(self):
        """
        Initialize the Vietnamese Query Module if not already initialized
        """
        if self.query_module is not None:
            return
            
        try:
            # Try to get embedding module and memory manager from server modules
            memory_manager = None
            embedding_module = None
            try:
                # Import here to avoid circular imports
                from backend.services.processing.server import modules
                if hasattr(modules, 'cuda_memory_manager') and modules.cuda_memory_manager:
                    memory_manager = modules.cuda_memory_manager
                    logger.debug("Using shared CUDA Memory Manager from server")
                if hasattr(modules, 'embedding_module') and modules.embedding_module:
                    embedding_module = modules.embedding_module
                    logger.debug("Using shared Embedding Module from server")
            except (ImportError, AttributeError) as e:
                logger.warning(f"Could not import modules from server: {e}")
            
            # Create embedding module only if not available from server
            if not embedding_module:
                logger.info("Creating new VietnameseEmbeddingModule for Gmail handler")
                embedding_module = VietnameseEmbeddingModule(
                    qdrant_host=settings.QDRANT_HOST,
                    qdrant_port=settings.QDRANT_PORT,
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    dense_model_name=settings.DENSE_MODEL_NAME,
                    sparse_model_name=settings.SPARSE_MODEL_NAME,
                    reranker_model_name=settings.RERANKER_MODEL_NAME,
                    vector_size=settings.VECTOR_SIZE,
                    memory_manager=memory_manager 
                )
            
            self.query_module = create_query_module(
                embedding_module=embedding_module,
                deepseek_api_key=self.deepseek_api_key,
                memory_manager=memory_manager,  
                deepseek_model=self.deepseek_model,
                limit=5,
                candidates_limit=10,
                dense_weight=0.8,
                sparse_weight=0.2,
                normalization="min_max",
                candidates_multiplier=3
            )
            
            logger.debug(f"Vietnamese Query Module initialized with hybrid search and reranking")
            
        except Exception as e:
            logger.error(f"Error initializing Vietnamese Query Module: {e}")
            raise

    def authenticate(self) -> None:
        creds = None
        
        # Check if token file exists and load it directly
        if os.path.exists(self.token_path):
            try:
                # Load token data
                token_data = json.load(open(self.token_path))
                
                # Create credentials using the token data
                creds = Credentials.from_authorized_user_info(token_data)
                
                # If token is expired but has refresh token, refresh it
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Save the refreshed token
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                    logger.info(f"Refreshed and saved authentication token to {self.token_path}")
            except Exception as e:
                logger.error(f"Error loading or refreshing token file: {e}")
                raise
        else:
            logger.error(f"Token file not found at {self.token_path}")
            raise FileNotFoundError(f"Token file not found: {self.token_path}")
                
        # Build Gmail service
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Successfully authenticated with Gmail API")
            
            # Initialize managers after authentication
            self._initialize_managers()
        except Exception as e:
            logger.error(f"Error building Gmail service: {e}")
            raise
            
    async def process_unread_email(self) -> List[Dict[str, Any]]:
        """
        Process unread emails using new optimized logic with Gemini conversation.
        
        Returns:
            List of processed email thread information
            
        Raises:
            Exception: If processing emails fails
        """
        if not self.service:
            try:
                self.authenticate()
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                return []
                
        try:
            # Get unread messages
            results = self.service.users().messages().list(
                userId=self.user_id, 
                q="is:unread").execute()
                
            messages = results.get('messages', [])
            
            if not messages:
                logger.debug("No unread messages found")
                return []
            
            # Group messages by thread_id
            thread_groups = {}
            for message in messages:
                msg = self.service.users().messages().get(
                    userId=self.user_id, 
                    id=message['id']).execute()
                    
                thread_id = msg['threadId']
                if thread_id not in thread_groups:
                    thread_groups[thread_id] = []
                thread_groups[thread_id].append(msg)
            
            logger.info(f"Found {len(messages)} unread emails in {len(thread_groups)} threads")
            
            processed_results = []
            
            # Process each thread
            for thread_id, thread_messages in thread_groups.items():
                try:
                    result = await self._process_thread(thread_id, thread_messages)
                    if result:
                        processed_results.append(result)
                except Exception as e:
                    logger.error(f"Error processing thread {thread_id}: {e}")
                    continue
            
            return processed_results
            
        except HttpError as e:
            logger.error(f"Error fetching emails: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return []
            
    def _get_email_body(self, message: Dict) -> str:
        """
        Extract email body from Gmail message, including processing images with Gemini
        
        Args:
            message: Gmail message object
            
        Returns:
            Processed email body content
        """
        try:
            message_id = message.get('id')
            payload = message.get('payload', {})
            
            email_text = extract_text_content(payload)
            
            image_attachments = extract_image_attachments(self.service, self.user_id, payload, message_id)
            
            # Process attachments with Gemini if present
            if image_attachments:
                try:
                    logger.info(f"Processing {len(image_attachments)} images with Gemini")
                    return self.gemini_processor.process_email_with_attachments(
                        email_text=email_text, 
                        image_attachments=image_attachments,
                        pdf_attachments=[]
                    )
                except Exception as e:
                    logger.error(f"Gemini error: {e}")
            
            # Add image info if present
            if image_attachments:
                image_info = f"\n\n=== ẢNH ĐÍNH KÈM ===\n"
                for i, img in enumerate(image_attachments, 1):
                    image_info += f"📷 Ảnh {i}: {img.get('filename', f'image_{i}')}\n"
                return email_text + image_info
            
            return email_text
            
        except Exception as e:
            logger.error(f"Error extracting email body: {e}")
            return "[Lỗi trích xuất nội dung email]"

    async def _process_thread(self, thread_id: str, thread_messages: List[Dict]) -> Optional[Dict[str, Any]]:
        try:
            logger.info(f"Processing thread {thread_id} with {len(thread_messages)} messages")
            
            existing_draft_id = self.draft_monitor.check_existing_draft(thread_id)
            if existing_draft_id:
                logger.info(f"Found existing draft {existing_draft_id}, deleting")
                self.draft_monitor.delete_draft(existing_draft_id)
            
            thread_info = self.metadata_db.get_gmail_thread_info(thread_id)
            last_processed_message_id = thread_info.get('last_processed_message_id') if thread_info else None
            
            all_thread_emails = await self._fetch_thread_emails_with_attachments(
                thread_id, last_processed_message_id
            )
            
            if not all_thread_emails:
                logger.warning(f"No emails to process for thread {thread_id}")
                return None
            
            conversation = await self._create_gemini_conversation_for_thread(all_thread_emails)
            if not conversation:
                logger.error(f"Failed to create Gemini conversation for thread {thread_id}")
                return None
            
            questions, context_summary = await self._extract_questions_with_gemini(conversation, all_thread_emails)
            
            if not questions:
                logger.info(f"No questions found in thread {thread_id}")
                return {"thread_id": thread_id, "status": "no_questions"}
            
            if self.query_module is None:
                self._init_query_module()
            
            summarized_results = []
            for i in range(0, len(questions), 2):
                group = questions[i:i+2]
                logger.debug(f"Processing question group {i//2 + 1}: {len(group)} questions")
                
                group_info = ""
                group_queries = []
                
                for j, question in enumerate(group):
                    group_queries.append(question)
                    
                    search_results = self.query_module.process_single_query(question)
                    
                    if search_results:
                        group_info += f"Câu hỏi {j+1}: {question}\n"
                        for k, result_item in enumerate(search_results):
                            content = result_item.get("content", "") if isinstance(result_item, dict) else str(result_item)
                            metadata = result_item.get("metadata", {}) if isinstance(result_item, dict) else {}
                            file_created_at = metadata.get("file_created_at")
                            source = metadata.get("source")
                            
                            group_info += f"Tài liệu {k+1}:"
                            if file_created_at:
                                group_info += f" (Cập nhật: {file_created_at})"
                            if source and not source.startswith("gmail_thread"):
                                group_info += f" [Nguồn: {source}]"
                            group_info += f"\n{content}\n\n"
                    else:
                        group_info += f"Câu hỏi {j+1}: {question}\nKhông tìm thấy thông tin liên quan.\n\n"
                
                summarization_prompt = f"""
                Hãy tóm tắt lại các nội dung liên quan đến các câu hỏi sau một cách chính xác, đầy đủ thông tin, súc tích:
                
                Các câu hỏi: {', '.join(group_queries)}
                
                Thông tin liên quan:
                {group_info}
                
                LƯU Ý QUAN TRỌNG:
                - Nếu có nhiều tài liệu về cùng một chủ đề với các ngày cập nhật khác nhau, chỉ sử dụng thông tin từ tài liệu có ngày cập nhật mới nhất và thêm thông tin trích dẫn ngày cập nhật đó.
                - Khi có thông tin nguồn tài liệu, hãy ghi rõ nguồn trong tóm tắt để có thể trích dẫn sau này.
                - Đối với thông tin chỉ có một tài liệu hoặc nhiều tài liệu cùng ngày cập nhật hoặc không có ngày cập nhật rõ ràng thì không cần ghi ngày cập nhật.
                """
                
                try:
                    summary_response = await self._ask_gemini(conversation, summarization_prompt)
                    summarized_results.append({
                        "queries": group_queries,
                        "summary": summary_response
                    })
                except Exception as e:
                    logger.error(f"Error summarizing group {group_queries}: {e}")
                    summarized_results.append({
                        "queries": group_queries,
                        "summary": f"Lỗi xử lý thông tin cho các câu hỏi: {', '.join(group_queries)}"
                    })
            
            email_response = await self._generate_email_response_with_gemini(
                conversation, all_thread_emails, summarized_results
            )
            
            conversation = None
            
            newest_email = thread_messages[-1]
            headers = {header['name']: header['value'] 
                      for header in newest_email['payload']['headers']}
            to_address = headers.get('From', '')
            subject = headers.get('Subject', '')
            
            draft_id = await self.create_draft_email(
                to=to_address,
                subject=subject,
                body=email_response,
                thread_id=thread_id
            )
            
            if draft_id:
                newest_message_id = newest_email['id']
                self.metadata_db.upsert_gmail_thread(
                    thread_id=thread_id,
                    context_summary=context_summary,
                    current_draft_id=draft_id,
                    last_processed_message_id=newest_message_id
                )
                
                marked_count = 0
                for msg in thread_messages:
                    try:
                        self.mark_as_read(msg['id'])
                        marked_count += 1
                    except Exception as mark_error:
                        logger.error(f"Failed to mark message {msg['id']} as read: {mark_error}")
                
                logger.info(f"Successfully processed thread {thread_id}, draft ID: {draft_id}, marked {marked_count}/{len(thread_messages)} messages as read")
                
                return {
                    "thread_id": thread_id,
                    "draft_id": draft_id,
                    "processed_messages": marked_count,
                    "context_summary": context_summary,
                    "status": "success"
                }
            else:
                logger.error(f"Failed to create draft for thread {thread_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error in _process_thread for thread {thread_id}: {e}")
            return None

    
    def mark_as_read(self, message_id: str) -> None:
        """
        Mark an email as read.
        
        Args:
            message_id: Gmail message ID
            
        Raises:
            Exception: If marking as read fails
        """
        try:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked message {message_id} as read")
        except Exception as e:
            logger.error(f"Error marking message as read: {e}")
            raise
            

    async def _fetch_thread_emails_with_attachments(self, thread_id: str, last_processed_message_id: str = None) -> List[Dict[str, Any]]:
        try:
            thread_messages = self.service.users().threads().get(
                userId=self.user_id, 
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread_messages.get('messages', [])
            
            if not messages:
                return []
            
            filtered_messages = []
            if last_processed_message_id:
                found_last = False
                for message in messages:
                    if message['id'] == last_processed_message_id:
                        found_last = True
                        continue
                    if found_last:
                        filtered_messages.append(message)
                
                if not found_last:
                    logger.warning(f"Last processed message {last_processed_message_id} not found, processing all messages")
                    filtered_messages = messages
            else:
                filtered_messages = messages
            
            if not filtered_messages:
                logger.info(f"No new messages to process for thread {thread_id}")
                return []
            
            processed_emails = []
            for message in filtered_messages:
                try:
                    headers = {h['name']: h['value'] for h in message['payload']['headers']}
                    
                    # Extract text content
                    email_text = extract_text_content(message['payload'])
                    
                    # Extract all attachments (images and PDFs)
                    attachments = extract_all_attachments(
                        self.service, self.user_id, message['payload'], message['id']
                    )
                    
                    # Process with Gemini if attachments exist
                    if attachments:
                        image_attachments = [att for att in attachments if att.get('attachment_type') == 'image']
                        pdf_attachments = [att for att in attachments if att.get('attachment_type') == 'pdf']
                        
                        try:
                            processed_content = self.gemini_processor.process_email_with_attachments(
                                email_text=email_text, 
                                image_attachments=image_attachments,
                                pdf_attachments=pdf_attachments
                            )
                        except Exception as e:
                            logger.error(f"Gemini processing failed for message {message['id']}: {e}")
                            processed_content = email_text + f"\n--- Lỗi xử lý đính kèm: {str(e)} ---"
                    else:
                        processed_content = email_text
                    
                    processed_emails.append({
                        'id': message['id'],
                        'from': headers.get('From', ''),
                        'to': headers.get('To', ''),
                        'subject': headers.get('Subject', ''),
                        'date': headers.get('Date', ''),
                        'content': processed_content,
                        'original_text': email_text,
                        'has_attachments': len(attachments) > 0,
                        'attachment_count': len(attachments)
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing message {message['id']}: {e}")
                    continue
            
            logger.info(f"Processed {len(processed_emails)} emails from thread {thread_id}")
            return processed_emails
            
        except Exception as e:
            logger.error(f"Error fetching thread emails for {thread_id}: {e}")
            return []

    async def _create_gemini_conversation_for_thread(self, thread_emails: List[Dict[str, Any]]) -> Optional[Any]:
        try:
            import google.generativeai as genai
            
            gmail_address = settings.GMAIL_EMAIL_ADDRESS 
            system_message = f"""
Bạn là trợ lý AI chuyên nghiệp hỗ trợ {gmail_address} trong việc phân tích và xử lý email từ sinh viên.

THÔNG TIN QUAN TRỌNG:
- Bạn đang hỗ trợ tài khoản: {gmail_address}
- Vai trò: Trợ lý phòng công tác sinh viên
- Nhiệm vụ: Phân tích email, tóm tắt nội dung, trích xuất câu hỏi và tạo phản hồi chuyên nghiệp

NGUYÊN TẮC HOẠT ĐỘNG:
1. Phân tích toàn bộ thread email để hiểu context đầy đủ
2. Tóm tắt nội dung một cách chi tiết và chính xác
3. Trích xuất các câu hỏi chưa được giải đáp từ sinh viên
4. Tạo phản hồi chuyên nghiệp, thân thiện nhưng trang trọng
5. Đảm bảo thông tin chính xác và cập nhật

Hãy sẵn sàng phân tích thread email.
"""
            
            model = genai.GenerativeModel("gemini-2.0-flash")
            chat = model.start_chat(history=[])
            
            # Send system message
            response = chat.send_message(system_message)
            
            logger.info("Successfully created Gemini conversation for thread analysis")
            return chat
            
        except Exception as e:
            logger.error(f"Error creating Gemini conversation: {e}")
            return None

    async def _extract_questions_with_gemini(self, conversation: Any, thread_emails: List[Dict[str, Any]]) -> tuple[List[str], str]:
        """
        Extract questions and create context summary using Gemini.
        
        Args:
            conversation: Gemini conversation object
            thread_emails: List of thread email data
            
        Returns:
            Tuple of (questions_list, context_summary)
        """
        try:
            # Prepare thread content for analysis
            thread_content = ""
            for i, email in enumerate(thread_emails, 1):
                thread_content += f"""
=== EMAIL {i} ===
Từ: {email['from']}
Đến: {email['to']}
Tiêu đề: {email['subject']}
Ngày: {email['date']}
Nội dung:
{email['content']}

"""
            
            analysis_prompt = f"""
Hãy phân tích thread email sau và thực hiện 2 nhiệm vụ:

1. TÓM TẮT CONTEXT: Tạo tóm tắt chi tiết, đầy đủ thông tin về toàn bộ thread email (đối với nội dung từ attachment thì cần ngắn gọn, súc tích nhưng vẫn đầy đủ thông tin bổ trợ cho email của người hỏi)

2. TRÍCH XUẤT CÂU HỎI: Tìm tất cả các câu hỏi/yêu cầu thông tin từ sinh viên mà chưa được giải đáp hoặc cần thông tin thêm

THREAD EMAIL:
{thread_content}

LƯU Ý QUAN TRỌNG:
- Chỉ trích xuất câu hỏi từ email sinh viên (không phải từ email phản hồi của phòng công tác sinh viên)
- Câu hỏi phải rõ ràng và cần thông tin cụ thể
- Bỏ qua các lời chào hỏi, cảm ơn đơn thuần
- Mỗi câu hỏi phải hoàn chỉnh và có thể tìm kiếm được

Trả về JSON với format:
{{
    "context_summary": "Tóm tắt chi tiết toàn bộ thread email...",
    "questions": [
        "Câu hỏi 1 được viết rõ ràng và hoàn chỉnh",
        "Câu hỏi 2 được viết rõ ràng và hoàn chỉnh",
        ...
    ]
}}

CHỈ TRẢ VỀ JSON VALID:
"""
            
            response = conversation.send_message(analysis_prompt)
            response_text = response.text.strip()
            
            # Clean and parse JSON
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            try:
                data = json.loads(response_text)
                questions = data.get("questions", [])
                context_summary = data.get("context_summary", "")
                
                # Filter out empty questions
                questions = [q.strip() for q in questions if q.strip()]
                
                logger.info(f"Extracted {len(questions)} questions and context summary")
                return questions, context_summary
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini JSON response: {e}")
                logger.error(f"Response text: {response_text}")
                
                # Fallback: try to extract basic info
                fallback_summary = f"Thread email với {len(thread_emails)} tin nhắn"
                fallback_questions = []
                
                return fallback_questions, fallback_summary
            
        except Exception as e:
            logger.error(f"Error extracting questions with Gemini: {e}")
            return [], "Lỗi phân tích thread email"

    async def _ask_gemini(self, conversation: Any, prompt: str) -> str:
        try:
            response = conversation.send_message(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error asking Gemini: {e}")
            return f"Lỗi khi hỏi Gemini: {str(e)}"

    async def _generate_email_response_with_gemini(self, conversation: Any, thread_emails: List[Dict[str, Any]], summarized_results: List[Dict]) -> str:
        """
        Generate email response using Gemini with search results.
        
        Args:
            conversation: Gemini conversation object
            thread_emails: Original thread emails
            summarized_results: Results from Vietnamese Query Module
            
        Returns:
            Generated email response text
        """
        try:
            # Prepare unread student emails content
            student_questions = ""
            for email in thread_emails:
                if email['from'] and settings.GMAIL_EMAIL_ADDRESS not in email['from']:  # Student email
                    student_questions += f"Từ sinh viên: {email['content']}\n\n"
            
            email_prompt = f"""
Dựa trên cuộc hội thoại email và thông tin đã tìm được, hãy soạn một email phản hồi chuyên nghiệp cho sinh viên.

NỘI DUNG CÂU HỎI TỪ SINH VIÊN:
{student_questions}

THÔNG TIN TÌM ĐƯỢC:
"""
            for i, result in enumerate(summarized_results, 1):
                email_prompt += f"Nhóm thông tin {i}: {result['summary']}\n"
            
            email_prompt += f"""

YÊU CẦU SOẠN EMAIL:
- Viết email phản hồi bằng tiếng Việt chuẩn, chuyên nghiệp
- Định dạng: văn bản thuần (plain text), KHÔNG dùng markdown
- Cấu trúc: lời chào, nội dung trả lời từng câu hỏi, lời kết thân thiện
- Ghi rõ ngày cập nhật thông tin nếu có
- Trích dẫn nguồn thông tin ở cuối email nếu cần
- Nếu thiếu thông tin, hướng dẫn sinh viên liên hệ bộ phận phù hợp
- Ký tên: "{settings.GMAIL_EMAIL_ADDRESS or 'Phòng Công tác Sinh viên'}"

CHỈ TRẢ VỀ NỘI DUNG EMAIL:
"""
            
            response = conversation.send_message(email_prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Error generating email response with Gemini: {e}")
            return f"Xin lỗi, có lỗi xảy ra khi tạo email phản hồi. Vui lòng liên hệ trực tiếp để được hỗ trợ.\n\nTrân trọng,\n{settings.GMAIL_EMAIL_ADDRESS or 'Phòng Công tác Sinh viên'}"

    async def create_draft_email(self, to: str, subject: str, body: str, thread_id: str = None) -> str:
        """
        Create a draft email in Gmail.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            thread_id: Thread ID for linking draft to specific thread
            
        Returns:
            Draft ID if successful, None if failed
            
        Raises:
            Exception: If creating draft fails
        """
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = f"Re: {subject}"
            
            msg = MIMEText(body)
            message.attach(msg)
            
            encoded_message = base64.urlsafe_b64encode(
                message.as_bytes()).decode()
            
            draft_body = {'message': {'raw': encoded_message}}
            
            if thread_id:
                draft_body['message']['threadId'] = thread_id
                logger.info(f"Linking draft to thread: {thread_id}")
            else:
                logger.warning("No thread_id provided - draft will not be linked to any thread")
                
            draft = self.service.users().drafts().create(
                userId=self.user_id,
                body=draft_body
            ).execute()
            
            draft_id = draft['id']
            
            logger.info(f"Draft created with ID: {draft_id} {'(linked to thread: ' + thread_id + ')' if thread_id else '(no thread link)'}")
            return draft_id
            
        except Exception as e:
            logger.error(f"Error creating draft: {e}")
            raise
            
    
    def process_text_with_vietnamese_query_module(self, text_content: str) -> str:
        """
        Process general text content with Vietnamese Query Module and generate comprehensive response
        
        Args:
            text_content: Input text content to process
            
        Returns:
            str: Comprehensive response with information and sources
        """
        try:
            if self.query_module is None:
                self._init_query_module()
            
            logger.info("Processing text with Vietnamese Query Module")
            results, conversation = self.query_module.process_text(text_content)
            
            if not results:
                logger.warning("No results from Vietnamese Query Module for text")
                return "Không tìm thấy thông tin liên quan đến nội dung của bạn."
            
            # Validate conversation context
            if not conversation:
                logger.error("No conversation context available from query module")
                return "Lỗi: Không có context cuộc hội thoại để xử lý văn bản."
            
            logger.info(f"Successfully obtained conversation context and {len(results)} query results")
            
            logger.info(f"Summarizing {len(results)} results from query module")
            summarized_results = []
            
            for i in range(0, len(results), 2):
                group = results[i:i+2]  # Get group of 2 (or 1 if odd number)
                logger.debug(f"Processing group {i//2 + 1}: {len(group)} queries")
                
                group_info = ""
                group_queries = []
                
                for j, result in enumerate(group):
                    query = result.original_query
                    group_queries.append(query)
                    
                    # Format information for this query
                    if result.results:
                        group_info += f"Câu hỏi {j+1}: {query}\n"
                        for k, result_item in enumerate(result.results):
                            # Extract content and metadata
                            content = result_item.get("content", "") if isinstance(result_item, dict) else str(result_item)
                            metadata = result_item.get("metadata", {}) if isinstance(result_item, dict) else {}
                            file_created_at = metadata.get("file_created_at")
                            source = metadata.get("source")
                            
                            group_info += f"Tài liệu {k+1}:"
                            if file_created_at:
                                group_info += f" (Cập nhật: {file_created_at})"
                            if source and not source.startswith("gmail_thread"):
                                group_info += f" [Nguồn: {source}]"
                            group_info += f"\n{content}\n\n"
                    else:
                        group_info += f"Câu hỏi {j+1}: {query}\nKhông tìm thấy thông tin liên quan.\n\n"
                
                summarization_prompt = f"""
                Hãy tóm tắt lại các nội dung liên quan đến các câu hỏi và context sau một cách chính xác, đầy đủ thông tin, súc tích:
                Context: {text_content}
                
                Các câu hỏi: {', '.join(group_queries)}
                
                Thông tin liên quan:
                {group_info}
                
                LƯU Ý QUAN TRỌNG:
                - Nếu có nhiều tài liệu về cùng một chủ đề với các ngày cập nhật khác nhau, chỉ sử dụng thông tin từ tài liệu có ngày cập nhật mới nhất, và ghi rõ ngày cập nhật đó trong tóm tắt (ví dụ: "Theo thông tin cập nhật ngày 15/03/2024, thủ tục làm bằng tốt nghiệp yêu cầu...").
                - Các nội dung không trùng lặp thì không cần ghi rõ ngày cập nhật.
                - Khi có thông tin nguồn tài liệu, giữ nguyên thông tin nguồn tài liệu để trích dẫn bằng footnotes ở cuối nội dung.
                """
                
                # Use conversation memory to maintain context
                if conversation and self.deepseek_client:
                    try:
                        summary_response = self.deepseek_client.send_message(
                            conversation=conversation,
                            message=summarization_prompt,
                            temperature=0.3,
                            max_tokens=8000,
                            error_default=f"Không tìm được thông tin cho các câu hỏi: {', '.join(group_queries)}"
                        )
                    except Exception as e:
                        logger.error(f"Error in conversation-based summarization for queries {group_queries}: {e}")
                        summary_response = f"Lỗi xử lý thông tin cho các câu hỏi: {', '.join(group_queries)}"
                else:
                    logger.error("No conversation context available for summarization")
                    summary_response = f"Không có context xử lý cho các câu hỏi: {', '.join(group_queries)}"
                
                summarized_results.append({
                    "queries": group_queries,
                    "summary": summary_response
                })
            
            response_prompt = f"""Bạn là một trợ lý AI hỗ trợ 
Dưới đây là nội dung cần xử lý:

{text_content}

Dựa trên nội dung và thông tin tìm thấy, hãy tạo một phản hồi đầy đủ:
"""
            for i, summary in enumerate(summarized_results):
                response_prompt += f"Nhóm thông tin {i+1}: {summary['summary']}\n"
            
            response_prompt += """
Dựa trên các thông tin trên, hãy tạo một phản hồi đầy đủ:
- Trình bày bằng tiếng Việt chuẩn, đúng chính tả, dễ hiểu.
- ĐẶC BIỆT QUAN TRỌNG: Viết phản hồi dưới dạng văn bản thuần (plain text), KHÔNG sử dụng markdown format hay bất kỳ định dạng nào khác.
- Trả lời lần lượt từng câu hỏi hoặc vấn đề được đặt ra, dựa vào thông tin đã tóm tắt.
- ĐẶC BIỆT QUAN TRỌNG: Nếu biết thông tin được cập nhật vào ngày nào (có ngày cập nhật cụ thể), hãy ghi rõ ngày cập nhật đó trong câu trả lời để người dùng biết đây là thông tin mới nhất. Ví dụ: "Theo thông tin cập nhật ngày 15/03/2024, quy trình đăng ký học phần đã thay đổi..."
- ĐẶC BIỆT QUAN TRỌNG: Khi có thông tin nguồn tài liệu, hãy trích dẫn nguồn thông tin ở cuối phản hồi và đánh dấu footnotes ở phần thông tin.
- Đối với các thông tin không có ngày cập nhật cụ thể, trả lời bình thường không cần ghi ngày.
- Đảm bảo phản hồi có cấu trúc rõ ràng: giới thiệu ngắn, nội dung chính, kết luận.

Viết phản hồi ngay dưới đây (chỉ trả về nội dung thuần (plain text)):
"""
            
            # Use conversation memory for final response generation
            if conversation and self.deepseek_client:
                try:
                    final_response = self.deepseek_client.send_message(
                        conversation=conversation,
                        message=response_prompt,
                        temperature=0.5,
                        max_tokens=4000,
                        error_default="Có lỗi xảy ra khi tạo phản hồi."
                    )
                except Exception as e:
                    logger.error(f"Error in conversation-based response generation: {e}")
                    final_response = "Xin lỗi, có lỗi xảy ra trong quá trình tạo phản hồi. Vui lòng thử lại sau."
            else:
                logger.error("No conversation context available for response generation")
                final_response = "Không có context cuộc hội thoại để tạo phản hồi."
            
            return final_response
            
        except Exception as e:
            logger.warning(f"Error processing text with Vietnamese Query Module: {e}")
            return "Xin lỗi, có lỗi xảy ra khi xử lý văn bản. Vui lòng thử lại sau."



    async def run(self) -> None:
        
        if not self.service:
            self.authenticate()
            
        if not self.draft_monitor or not self.api_monitor:
            self._initialize_managers()
        
        if not self.background_worker:
            self._init_indexing_worker()
        
        if not self.cleanup_worker:
            self._init_cleanup_worker()
        
        logger.info("Starting Gmail monitoring with API polling")
        
        await self.api_monitor.start_monitoring()
        logger.info("Gmail API polling monitoring started")
                
async def start_gmail_monitoring(gmail_handler=None):
    if gmail_handler:
        logger.info("Using injected Gmail handler for monitoring")
        handler = gmail_handler
    else:
        logger.info("Creating new Gmail handler for monitoring")
        handler = GmailHandler()
    
    await handler.run()
