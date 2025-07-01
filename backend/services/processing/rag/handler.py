import os
import base64
import json
import re
import asyncio
import logging
import time
import uuid
import google.generativeai as genai
import functools
import tempfile

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
from backend.common.config import settings
from backend.adapter.sql.metadata import get_metadata_db

from backend.services.processing.rag.draft_monitor import EmailDraftMonitor

from backend.services.processing.rag.common.utils import (
    create_deepseek_client, DeepSeekAPIClient, 
    extract_text_content, extract_all_attachments,
    call_deepseek_async
)

from backend.services.processing.rag.extractors.gemini.gemini_email_processor import GeminiEmailProcessor
from backend.services.processing.rag.gmail_api_monitor import create_gmail_api_monitor
from backend.services.processing.rag.gmail_indexing_worker import GmailIndexingWorker
from backend.services.processing.rag.gmail_cleanup_worker import GmailCleanupWorker

logger = logging.getLogger(__name__)

# Create log directory for query processing
QUERY_LOG_DIR = Path(__file__).resolve().parents[4] / "logs" / "query_processing"
QUERY_LOG_DIR.mkdir(parents=True, exist_ok=True)

# A simple structure to mimic QueryResult for logging purposes
class QueryResultLog:
    def __init__(self, original_query, results):
        self.original_query = original_query
        self.results = results

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
            
            self.gemini_processor = GeminiEmailProcessor()
        except Exception as e:
            logger.error(f"Gemini initialization failed: {e}")
            raise Exception(f"Required Gemini processor failed to initialize: {e}")
        
        self.deepseek_api_key = settings.DEEPSEEK_API_KEY
        self.deepseek_api_url = settings.DEEPSEEK_API_URL
        self.deepseek_model = settings.DEEPSEEK_MODEL
        
        self.deepseek_client = None
        
        self.query_module = None
        
        self.metadata_db = get_metadata_db()
        
        self.draft_monitor = None
        self.api_monitor = None
        
        self.background_worker = None
        self.cleanup_worker = None
        
        if not self.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY not set in settings")
    
    def _get_deepseek_client(self):
        """Initializes and returns the DeepSeek client, creating it if it doesn't exist."""
        if self.deepseek_client is None and self.deepseek_api_key:
            self.deepseek_client = create_deepseek_client(
                deepseek_api_key=self.deepseek_api_key,
                deepseek_api_url=self.deepseek_api_url,
                deepseek_model=self.deepseek_model
            )
        return self.deepseek_client

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
        
        logger.debug("Draft monitor and Gmail API monitor initialized")

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
                logger.debug("Using shared embedding module from query module")
            
            self.background_worker = GmailIndexingWorker(
                gmail_service=self.service,
                user_id=self.user_id,
                gemini_processor=self.gemini_processor,
                embedding_module=embedding_module
            )
            self.background_worker.start()
            logger.debug("Gmail indexing worker initialized and started")
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
                logger.debug("Using shared embedding module from query module")
            
            self.cleanup_worker = GmailCleanupWorker(embedding_module=embedding_module)
            self.cleanup_worker.start()
            logger.debug("Gmail cleanup worker initialized and started")
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
                    logger.debug(f"Using shared Embedding Module from server - will use collection switching for {settings.EMAIL_QA_COLLECTION}")
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
                candidates_limit=15,
                dense_weight=0.8,
                sparse_weight=0.2,
                normalization="min_max",
                candidates_multiplier=4
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
                    logger.debug(f"Refreshed and saved authentication token to {self.token_path}")
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
            
            logger.debug(f"Found {len(messages)} unread emails in {len(thread_groups)} threads")
            
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
            
    async def _process_thread(self, thread_id: str, thread_messages: List[Dict]) -> Optional[Dict[str, Any]]:
        uploaded_files_to_clean = []
        try:
            logger.debug(f"Processing thread {thread_id} with {len(thread_messages)} messages")
            
            # Generate unique session ID for this processing session
            session_id = f"thread_{thread_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            
            existing_draft_id = self.draft_monitor.check_existing_draft(thread_id)
            if existing_draft_id:
                logger.debug(f"Found existing draft {existing_draft_id}, deleting")
                self.draft_monitor.delete_draft(existing_draft_id)
            
            thread_info = self.metadata_db.get_gmail_thread_info(thread_id)
            last_processed_message_id = thread_info.get('last_processed_message_id') if thread_info else None
            existing_summary = thread_info.get('context_summary') if thread_info else None
            
            all_thread_emails = await self._fetch_thread_emails_with_attachments(
                thread_id, last_processed_message_id
            )
            
            if not all_thread_emails:
                logger.warning(f"No emails to process for thread {thread_id}")
                return None
            
            # Prepare email content for logging
            thread_text_content_for_logging = "\\n\\n---\\n\\n".join(
                f"From: {e['from']}\\nTo: {e['to']}\\nSubject: {e['subject']}\\nDate: {e['date']}\\n\\n{e['content']}" 
                for e in all_thread_emails
            )

            conversation = await self._create_gemini_conversation_for_thread(all_thread_emails)
            if not conversation:
                logger.error(f"Failed to create Gemini conversation for thread {thread_id}")
                return None
            
            questions, context_summary, uploaded_files_to_clean = await self._extract_questions_with_gemini(
                conversation, 
                all_thread_emails, 
                existing_summary=existing_summary
            )
            
            if not questions:
                logger.info(f"No questions found in thread {thread_id}")
                return {"thread_id": thread_id, "status": "no_questions"}
            
            if self.query_module is None:
                self._init_query_module()
            
            # Process all questions at once instead of grouping
            logger.debug(f"Processing {len(questions)} questions")
            
            content_evaluation_tasks = []
            all_query_results_for_logging = []
            
            for question in questions:
                # Search in both collections using optimized method
                search_results, qa_results = self._search_multiple_collections(question)
                
                # For logging
                all_results_for_question = search_results + qa_results
                all_query_results_for_logging.append(
                    QueryResultLog(original_query=question, results=all_results_for_question)
                )

                # Create evaluation and extraction tasks for main collection results
                for result_item in search_results:
                    content = result_item.get("content", "") if isinstance(result_item, dict) else str(result_item)
                    if content:
                        task = self._evaluate_and_extract_relevant_content(questions, content)
                        content_evaluation_tasks.append((question, result_item, task, "main"))
                
                # Create evaluation and extraction tasks for EMAIL_QA collection results  
                for qa_item in qa_results:
                    qa_content = qa_item.get("content", "") if isinstance(qa_item, dict) else str(qa_item)
                    if qa_content:
                        task = self._evaluate_and_extract_relevant_content(questions, qa_content)
                        content_evaluation_tasks.append((question, qa_item, task, "qa"))
            
            # Execute all evaluation and extraction tasks concurrently
            extracted_info = ""
            content_evaluation_data_for_logging = []
            if content_evaluation_tasks:
                logger.debug(f"Extracting information from {len(content_evaluation_tasks)} retrieved chunks...")
                evaluation_results = await asyncio.gather(*(task for _, _, task, _ in content_evaluation_tasks))
                
                for (question, chunk, task, source_type), extraction_result in zip(content_evaluation_tasks, evaluation_results):
                    content_evaluation_data_for_logging.append((question, chunk, extraction_result))
                    if extraction_result.get("is_relevant", False):
                        metadata = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}
                        file_created_at = metadata.get("file_created_at")
                        source = metadata.get("source")
                        
                        # Build source info
                        source_type_label = "tài liệu chính thức" if source_type == "main" else "Q&A trước đây"
                        source_info = f"**Trích xuất từ {source_type_label}:**"
                        
                        # Add source citation only for main collection
                        if source_type == "main" and source and not source.startswith("gmail_thread"):
                            source_info += f" [Nguồn: {source}]"
                        
                        # Add update date if available
                        if file_created_at:
                            source_info += f" (Cập nhật: {file_created_at})"
                        
                        # Format final output
                        extracted_info += f"""### Thông tin liên quan đến câu hỏi: "{question}"

{source_info}
---
{extraction_result['relevant_content']}
---

"""
            
            if not extracted_info:
                extracted_info = f"Không tìm thấy thông tin liên quan đến các câu hỏi: {', '.join(questions)}"
            
            extracted_results = [{
                "queries": questions,
                "extracted_content": extracted_info
            }]
            
            email_response = await self._generate_email_response_with_gemini(
                conversation, all_thread_emails, extracted_results, context_summary
            )
            
            # Save logs for this processing session
            self._save_query_processing_log(
                text_content=thread_text_content_for_logging,
                results=all_query_results_for_logging,
                content_evaluation_data=content_evaluation_data_for_logging,
                final_response=email_response,
                session_id=session_id
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
        finally:
            # Cleanup files
            if uploaded_files_to_clean:
                logger.debug(f"Cleaning up {len(uploaded_files_to_clean)} uploaded files for thread {thread_id}")
                for uploaded_file, temp_path in uploaded_files_to_clean:
                    try:
                        genai.delete_file(uploaded_file.name)
                        os.unlink(temp_path)
                    except Exception as e:
                        logger.warning(f"Failed to clean up file {uploaded_file.name if uploaded_file else 'N/A'} or temp path {temp_path}: {e}")

    
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

    def _process_email_content(self, message: Dict) -> Dict[str, Any]:
        try:
            payload = message['payload']
            headers = {h['name']: h['value'] for h in payload['headers']}
            
            original_text = extract_text_content(payload)
            attachments = extract_all_attachments(self.service, self.user_id, payload, message['id'])
            
            return {
                'id': message['id'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'content': original_text,  
                'attachments': attachments, 
                'has_attachments': len(attachments) > 0,
            }
            
        except Exception as e:
            logger.error(f"Error processing message {message.get('id')}: {e}")
            return None

    async def _fetch_thread_emails_with_attachments(self, thread_id: str, last_processed_message_id: str = None) -> List[Dict[str, Any]]:
        """Fetch and process thread emails with attachments - clean and simplified version"""
        try:
            # Fetch thread messages
            thread_messages = self.service.users().threads().get(
                userId=self.user_id, 
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread_messages.get('messages', [])
            if not messages:
                return []
            
            # Filter to get only new messages
            filtered_messages = self._filter_new_messages(messages, last_processed_message_id)
            if not filtered_messages:
                logger.info(f"No new messages to process for thread {thread_id}")
                return []
            
            # Process each message
            processed_emails = []
            for message in filtered_messages:
                processed_email = self._process_email_content(message)
                if processed_email: 
                    processed_emails.append(processed_email)
            
            logger.info(f"Processed {len(processed_emails)} emails from thread {thread_id}")
            return processed_emails
            
        except Exception as e:
            logger.error(f"Error fetching thread emails for {thread_id}: {e}")
            return []

    async def _create_gemini_conversation_for_thread(self, thread_emails: List[Dict[str, Any]]) -> Optional[Any]:
        try:
            system_instruction = f"""
# VAI TRÒ VÀ MỤC TIÊU
Bạn là một Trợ lý AI chuyên nghiệp, được thiết kế chuyên biệt để hỗ trợ tài khoản email {settings.GMAIL_EMAIL_ADDRESS} của Phòng Công tác Sinh viên. Nhiệm vụ chính của bạn là phân tích các luồng email từ sinh viên một cách chính xác, khách quan và hiệu quả để chuẩn bị cho các bước xử lý tiếp theo.

# CÁC NGUYÊN TẮC HOẠT ĐỘNG BẮT BUỘC
Bạn PHẢI tuân thủ nghiêm ngặt các nguyên tắc sau trong mọi phản hồi:

1.  **Objectivity:** Chỉ phân tích và trích xuất thông tin dựa trên dữ liệu được cung cấp trong email. Tuyệt đối không suy diễn, không thêm thông tin không có, và không đưa ra ý kiến cá nhân.
2.  **Precision:** Đảm bảo mọi thông tin được tóm tắt hoặc trích xuất đều chính xác tuyệt đối so với email gốc.
3.  **Task-Focus:** Luôn bám sát vào yêu cầu cụ thể của từng prompt theo sau. Không thực hiện các hành động không được yêu cầu.

# NĂNG LỰC CỐT LÕI
Bạn có khả năng hiểu sâu sắc ngữ cảnh của một cuộc hội thoại qua email, phân biệt được người gửi và người nhận, và nhận diện chính xác các câu hỏi, yêu cầu hoặc các điểm thông tin quan trọng.

Hãy sẵn sàng áp dụng các nguyên tắc và năng lực này để phân tích luồng email sẽ được cung cấp.
"""
            
            # Sử dụng system_instruction để thiết lập vai trò cho model
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



    async def _extract_questions_with_gemini(self, conversation: Any, thread_emails: List[Dict[str, Any]], existing_summary: Optional[str] = None) -> tuple[List[str], str, List[Tuple[Any, str]]]:
        """Extract questions and create context summary using Gemini File API."""
        try:
            prompt_parts = []
            thread_text = ""
            uploaded_files = []
            
            # Process each email
            for i, email in enumerate(thread_emails, 1):
                email_text = f"""
=== EMAIL {i} ===
Từ: {email['from']}
Đến: {email['to']}
Tiêu đề: {email['subject']}
Ngày: {email['date']}
Nội dung: {email['content']}
"""
                if email.get('attachments'):
                    email_text += "\n--- File đính kèm ---\n"
                    for att in email['attachments']:
                        email_text += f"- {att.get('filename', 'N/A')}\n"
                
                thread_text += email_text + "\n"
                
                # Upload attachments to Gemini
                for attachment in email.get('attachments', []):
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
                                uploaded_files.append((uploaded_file, temp_path))
                            else:
                                os.unlink(temp_path)
                                        
                        except Exception:
                            if 'temp_path' in locals():
                                try:
                                    os.unlink(temp_path)
                                except:
                                    pass

            # Create prompt
            analysis_prompt = (self._create_update_summary_prompt(thread_text, existing_summary) 
                             if existing_summary 
                             else self._create_new_summary_prompt(thread_text))

            full_prompt = [analysis_prompt] + prompt_parts
            
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
                                "context_summary": {
                                    "type": "string",
                                    "description": "Tóm tắt ngắn gọn của cuộc hội thoại và tri thức"
                                },
                                "questions": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    },
                                    "description": "Danh sách các câu hỏi được trích xuất"
                                }
                            },
                            "required": ["context_summary", "questions"]
                        }
                    }
                )
                
                # Parse JSON directly
                try:
                    data = json.loads(response.text.strip())
                    questions = [q.strip() for q in data.get("questions", []) if q.strip()]
                    context_summary = data.get("context_summary", "")
                    return questions, context_summary, uploaded_files
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from Gemini response: {e}\n---\n{response.text}\n---")
                    return [], f"Thread email với {len(thread_emails)} tin nhắn", uploaded_files
                    
            except Exception as e:
                logger.error(f"Error sending message to Gemini: {e}")
                return [], f"Thread email với {len(thread_emails)} tin nhắn", uploaded_files
                    
        except Exception as e:
            logger.error(f"Error extracting questions with Gemini: {e}")
            return [], "Lỗi phân tích thread email", uploaded_files
    
    def _create_update_summary_prompt(self, thread_content: str, existing_summary: str) -> str:
        """Creates a prompt to update a summary and extract questions from new emails in a thread."""
        return f"""
# VAI TRÒ VÀ MỤC TIÊU
Bạn là một Trợ lý AI chuyên nghiệp, có nhiệm vụ phân tích các email mới trong một luồng hội thoại và tích hợp chúng vào bối cảnh chung một cách chính xác. Mục tiêu cuối cùng là cập nhật tóm tắt và rút ra các câu hỏi mới để hệ thống có thể tìm kiếm thông tin trả lời.

# NHIỆM VỤ
Phân tích các email mới dưới đây. Trọng tâm của bạn là các câu hỏi và yêu cầu tường minh trong **nội dung email**. Các **file đính kèm (hình ảnh, PDF) chỉ đóng vai trò là bằng chứng hoặc thông tin bổ sung** cho các yêu cầu đó và **TUYỆT ĐỐI KHÔNG** được dùng để tự tạo ra câu hỏi mới.

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
        - **Yêu cầu:** Bản tóm tắt tri thức phải chi tiết, đầy đủ, khách quan và **TUYỆT ĐỐI KHÔNG** chứa thông tin định danh cá nhân (tên, MSSV), lời chào hỏi, hoặc các câu trao đổi không mang tính tri thức. Hãy tích hợp thông tin mới này với tóm tắt tri thức cũ (nếu có) để tạo ra một bản tổng hợp hoàn chỉnh.
3.  **Tái cấu trúc Câu hỏi Mới:**
    -   Xác định các câu hỏi hoặc yêu cầu **chỉ có trong nội dung của các email mới**.
    -   Tái cấu trúc mỗi câu hỏi thành một **truy vấn tìm kiếm độc lập, đầy đủ ngữ cảnh**.
    -   Loại bỏ Thông tin Cá nhân (PII) khỏi truy vấn.
    -   Sử dụng thông tin trong file đính kèm mới để làm giàu ngữ cảnh cho các câu hỏi.
    -   **KHÔNG** tạo câu hỏi từ tóm tắt cũ. Chỉ tập trung vào những gì mới được hỏi.

# VÍ DỤ CỤ THỂ
---
**Input (Tóm tắt bối cảnh hiện tại):**
"Sinh viên hỏi về thủ tục xin học bổng XYZ ||| Thông tin cần xử lý: thủ tục và giấy tờ cần thiết cho học bổng XYZ."

**Input (Email mới + file đính kèm là ảnh 'Giấy chứng nhận hộ nghèo'):**
"Dạ em chào phòng CTSV, em đã chuẩn bị xong hồ sơ như hướng dẫn ạ. Em gửi file PDF đơn và giấy chứng nhận hộ nghèo. Nhờ phòng kiểm tra giúp em xem đã đủ chưa ạ?"

**Output (JSON):**
```json
{{
  "context_summary": "Sinh viên hỏi về thủ tục xin học bổng XYZ và đã nộp đơn cùng giấy chứng nhận hộ nghèo, muốn xác nhận hồ sơ đã đủ chưa ||| Thông tin cần xử lý: thủ tục và giấy tờ cần thiết cho học bổng XYZ, bao gồm đơn và giấy chứng nhận hộ nghèo. Cần xác định danh sách đầy đủ các giấy tờ.",
  "questions": [
    "danh sách đầy đủ các giấy tờ cần thiết cho hồ sơ học bổng XYZ khi có giấy chứng nhận hộ nghèo"
  ]
}}
```
---

# YÊU CẦU ĐẦU RA
Trả về hai phần: tóm tắt cuộc hội thoại cập nhật và danh sách các câu hỏi được trích xuất từ email mới.

# QUY TẮC RÀNG BUỘC
-   Tóm tắt phải khách quan, không suy diễn thông tin không có trong email và file đính kèm.
-   Nếu không có câu hỏi nào trong các email mới, hãy trả về một mảng rỗng cho "questions".
-   Luôn trả về cả 2 phần tóm tắt trong `context_summary`, ngay cả khi một trong hai phần trống.
"""
    
    def _create_new_summary_prompt(self, thread_content: str) -> str:
        """Creates a prompt to generate a new summary and extract questions from a thread."""
        return f"""
# VAI TRÒ VÀ MỤC TIÊU
Bạn là một Trợ lý AI chuyên nghiệp, có nhiệm vụ phân tích một luồng email lần đầu tiên để hiểu rõ bối cảnh và rút ra các câu hỏi hoặc yêu cầu chính, đồng thời trích xuất các thông tin tri thức hữu ích.

# NHIỆM VỤ
Phân tích kỹ lưỡng luồng email dưới đây. Trọng tâm của bạn là các câu hỏi và yêu cầu tường minh trong **nội dung email**. Các **file đính kèm (hình ảnh, PDF) chỉ đóng vai trò là bằng chứng hoặc thông tin bổ sung** cho các yêu cầu đó và **TUYỆT ĐỐI KHÔNG** được dùng để tự tạo ra câu hỏi mới.

# QUY TRÌNH SUY LUẬN VÀ THỰC HIỆN (BẮT BUỘC)
1.  **Tóm tắt Bối cảnh (2 Phần):**
    -   **Phần 1 - Tóm tắt cuộc hội thoại:** Đọc toàn bộ luồng email và tạo một bản tóm tắt khách quan về (các) vấn đề chính mà người gửi đưa ra và diễn biến cuộc hội thoại.
    -   **Phần 2 - Tóm tắt tri thức:** Dựa trên **toàn bộ luồng email**, hãy **chắt lọc và tổng hợp lại các thông tin hữu ích có thể tái sử dụng** được cung cấp trong các email phản hồi từ tài khoản `{settings.GMAIL_EMAIL_ADDRESS}`. Đây là phần CỰC KỲ QUAN TRỌNG, dùng để chunking cho RAG.
        - **Nguồn tri thức chính:** Nội dung trong các email được gửi **TỪ** `{settings.GMAIL_EMAIL_ADDRESS}` (ví dụ: các câu trả lời, hướng dẫn quy trình, thông báo, yêu cầu bổ sung giấy tờ...).
        - **Bối cảnh:** Sử dụng nội dung email của sinh viên (người hỏi) để làm rõ bối cảnh cho câu trả lời của phòng CTSV.
        - **Yêu cầu:** Bản tóm tắt tri thức phải chi tiết, đầy đủ, khách quan và **TUYỆT ĐỐI KHÔNG** chứa thông tin định danh cá nhân (tên, MSSV), lời chào hỏi, hoặc các câu trao đổi không mang tính tri thức. Tích hợp thông tin quan trọng từ file đính kèm vào phần này.
2.  **Tái cấu trúc Câu hỏi:**
    -   Xác định tất cả các câu hỏi hoặc yêu cầu tường minh của người gửi **từ nội dung email**.
    -   Đối với mỗi câu hỏi, hãy tái cấu trúc nó thành một **truy vấn tìm kiếm độc lập, đầy đủ ngữ cảnh**.
    -   **Chuyển đổi câu hỏi trạng thái:** Nếu sinh viên hỏi về tình trạng cụ thể (ví dụ: "Hồ sơ của em được duyệt chưa?"), hãy chuyển đổi nó thành một truy vấn chung về quy trình hoặc yêu cầu (ví dụ: "Quy trình xét duyệt hồ sơ gồm những bước nào và tiêu chuẩn là gì?").
    -   **Chuyển đổi "Thiếu" thành "Đủ":** Nếu sinh viên hỏi "cần bổ sung gì thêm?", hãy chuyển nó thành truy vấn về "danh sách đầy đủ các yêu cầu".
    -   **Loại bỏ Thông tin Cá nhân (PII):** Tất cả các truy vấn được tạo ra **TUYỆT ĐỐI KHÔNG** được chứa tên riêng, MSSV, hoặc bất kỳ thông tin định danh cá nhân nào khác.
    -   Sử dụng thông tin trong file đính kèm để làm giàu ngữ cảnh cho các câu hỏi đó.
    -   **QUAN TRỌNG:** Câu hỏi phải xuất phát từ nội dung email. **TUYỆT ĐỐI KHÔNG** tự tạo câu hỏi chỉ dựa vào nội dung file đính kèm.

# LUỒNG EMAIL CẦN PHÂN TÍCH
(Lưu ý: Các file đính kèm được cung cấp riêng và chỉ mang tính bổ trợ cho nội dung email)
---
{thread_content}
---

# VÍ DỤ CỤ THỂ
---
**Input (Email Content + file đính kèm là ảnh "Giấy xác nhận của bệnh viện"):**
"Kính gửi Phòng Công tác Sinh viên, em là Lê Thị C, MSSV 2020xxxx. Em viết email này để nộp hồ sơ xin học bổng ABC cho học kỳ 1 năm học 2024-2025. Em có đính kèm file PDF là đơn xin học bổng đã điền đầy đủ thông tin. Xin hỏi hồ sơ của em như vậy đã đủ chưa và khi nào có kết quả ạ? Em cảm ơn."

**Output (JSON):**
```json
{{
  "context_summary": "Sinh viên Lê Thị C (MSSV 2020xxxx) nộp hồ sơ xin học bổng ABC và hỏi về tính đầy đủ của hồ sơ cũng như thời gian công bố kết quả ||| Thông tin cần xử lý: yêu cầu về hồ sơ xin học bổng ABC học kỳ 1 2024-2025 và thời gian công bố kết quả. Sinh viên đã nộp đơn dạng PDF.",
  "questions": [
    "danh sách đầy đủ các giấy tờ cần thiết cho hồ sơ xin học bổng ABC",
    "thời gian dự kiến công bố kết quả học bổng ABC học kỳ 1 năm học 2024-2025"
  ]
}}
```
---

# YÊU CẦU ĐẦU RA
Trả về hai phần: tóm tắt cuộc hội thoại và danh sách các câu hỏi được trích xuất.

# QUY TẮC RÀNG BUỘC
-   Tập trung vào các câu hỏi trong email. File đính kèm dùng để cung cấp thêm chi tiết.
-   Tóm tắt và truy vấn phải khách quan, chỉ dựa vào thông tin được cung cấp.
-   Nếu không có câu hỏi nào, hãy trả về một mảng rỗng cho "questions".
-   Luôn trả về cả 2 phần tóm tắt trong `context_summary`, ngay cả khi một trong hai phần trống.
"""

    async def _ask_gemini(self, conversation: Any, prompt: str, temperature: float = 0.3, response_schema: Dict = None) -> str:
        try:
            generation_config = {"temperature": temperature}
            if response_schema:
                generation_config["response_mime_type"] = "application/json"
                generation_config["response_schema"] = response_schema
            
            response = conversation.send_message(
                prompt,
                generation_config=generation_config
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error asking Gemini: {e}")
            return f"Lỗi khi hỏi Gemini: {str(e)}"

    async def _generate_email_response_with_gemini(self, conversation: Any, thread_emails: List[Dict[str, Any]], extracted_results: List[Dict], context_summary: str) -> str:
        """
        Generate email response using Gemini with search results.
        
        Args:
            conversation: Gemini conversation object
            thread_emails: Original thread emails
            extracted_results: Results from evaluation and extraction process
            context_summary: Summary of the thread
            
        Returns:
            Generated email response text
        """
        try:
            # Prepare unread student emails content
            student_questions = ""
            for email in thread_emails:
                if email['from'] and settings.GMAIL_EMAIL_ADDRESS not in email['from']: 
                    student_questions += f"- Nội dung từ email của sinh viên: {email['content']}\\n"

            retrieved_information = ""
            for result in extracted_results:
                retrieved_information += f"{result['extracted_content']}\\n"
            
            email_prompt = f"""# VAI TRÒ
Bạn là một Trợ lý AI của Phòng Công tác Sinh viên, có nhiệm vụ soạn một email phản hồi duy nhất, chuyên nghiệp, và hữu ích để trả lời các câu hỏi của sinh viên dựa trên thông tin được cung cấp.

# BỐI CẢNH CUỘC HỘI THOẠI
Đây là tóm tắt của luồng email cho đến nay. Phần đầu là tóm tắt hội thoại, phần sau là tóm tắt tri thức đã biết.
---
{context_summary}
---

# CÁC CÂU HỎI MỚI NHẤT TỪ SINH VIÊN
Đây là nội dung các email mới nhất từ sinh viên cần được trả lời.
---
{student_questions}
---

# THÔNG TIN HỖ TRỢ ĐÃ TÌM KIẾM ĐƯỢC
Đây là các thông tin được trích xuất từ cơ sở tri thức để giúp bạn trả lời. Mỗi đoạn trích có thể đi kèm thông tin nguồn và ngày cập nhật.
---
{retrieved_information}
---

# NHIỆM VỤ
Dựa trên **TOÀN BỘ** thông tin trên (bối cảnh, câu hỏi mới, và thông tin hỗ trợ), hãy soạn một email phản hồi **DUY NHẤT** cho sinh viên.

# QUY TẮC SOẠN THẢO (BẮT BUỘC TUÂN THỦ)
1.  **Giọng văn:** Chuyên nghiệp, rõ ràng, hỗ trợ và đồng cảm với sinh viên.
2.  **Định dạng:** Chỉ sử dụng văn bản thuần túy (plain text), **KHÔNG** dùng Markdown.
3.  **Cấu trúc:**
    *   Bắt đầu bằng lời chào phù hợp (ví dụ: "Chào bạn,").
    *   Tổng hợp thông tin từ nhiều nguồn để trả lời **từng câu hỏi** của sinh viên một cách mạch lạc. Đừng chỉ liệt kê các đoạn trích.
    *   Ở cuối email, nếu có trích dẫn, thêm mục "NGUỒN THAM KHẢO".
    *   Kết thúc bằng lời kết thân thiện và chữ ký.
4.  **Xử lý thông tin và trích dẫn:**
    *   Nếu có nhiều thông tin về cùng một chủ đề, hãy ưu tiên và chỉ sử dụng thông tin có ngày cập nhật **gần đây nhất**. Phải nêu rõ ngày cập nhật trong câu trả lời (ví dụ: "Theo thông tin cập nhật ngày DD/MM/YYYY,...").
    *   Đối với thông tin từ `tài liệu chính thức` có `[Nguồn: ...]`, bạn **BẮT BUỘC** phải trích dẫn nguồn. Sử dụng footnote dạng số (ví dụ: `...nội dung [1].`) và liệt kê tất cả các nguồn ở cuối email dưới tiêu đề `NGUỒN THAM KHẢO: link nguồn`.
    *   Thông tin từ `Q&A trước đây` có thể dùng trực tiếp mà không cần trích dẫn nguồn.
    *   Nếu không có thông tin nào được trích xuất từ nguồn tham khảo, **TUYỆT ĐỐI KHÔNG** hiển thị mục "NGUỒN THAM KHẢO".
5.  **Trường hợp thiếu thông tin:** Nếu thông tin tìm được không đủ để trả lời một câu hỏi nào đó, hãy trung thực nêu rõ: "Về vấn đề [...], hiện tại hệ thống chưa có thông tin chi tiết. Bạn vui lòng liên hệ trực tiếp [...] để được hỗ trợ."
6.  **Chữ ký:** Kết thúc email bằng chữ ký sau:
Trân trọng,
Phòng Công tác Sinh viên

# YÊU CẦU ĐẦU RA
Trả về nội dung email phản hồi hoàn chỉnh dạng plain text.
"""
            
            if not conversation:
                logger.error("No conversation context available for response generation")
                raise Exception("No conversation context available for response generation")
            try:
                final_response = await self._ask_gemini(conversation, email_prompt, temperature=0.3)
                return final_response
            except Exception as e:
                logger.error(f"Error in conversation-based response generation: {e}")
                raise Exception(f"Error in conversation-based response generation: {e}")
        except Exception as e:
            logger.error(f"Error generating email response with Gemini: {e}")
            raise

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
                logger.debug(f"Linking draft to thread: {thread_id}")
            else:
                logger.warning("No thread_id provided - draft will not be linked to any thread")
                
            draft = self.service.users().drafts().create(
                userId=self.user_id,
                body=draft_body
            ).execute()
            
            draft_id = draft['id']
            
            logger.debug(f"Draft created with ID: {draft_id} {'(linked to thread: ' + thread_id + ')' if thread_id else '(no thread link)'}")
            return draft_id
            
        except Exception as e:
            logger.error(f"Error getting thread by draft ID: {e}")
            return None
            
    
    def _save_query_processing_log(self, text_content: str, results: List, content_evaluation_data: List, final_response: str, session_id: str) -> None:
        try:
            relevant_content_map = {}
            for query, chunk, extraction_result in content_evaluation_data:
                if extraction_result.get("is_relevant", False):
                    if query not in relevant_content_map:
                        relevant_content_map[query] = []
                    relevant_content_map[query].append(extraction_result.get("relevant_content", ""))
            
            for i, result in enumerate(results):
                query = result.original_query
                # Make filename safe for Windows and other filesystems
                safe_query_name = "".join(c if c.isalnum() else '_' for c in query).strip('_')[:50]
                if not safe_query_name:
                    safe_query_name = "query"
                query_folder_name = f"query_{i+1:02d}_{safe_query_name}"
                query_folder = QUERY_LOG_DIR / session_id / query_folder_name
                query_folder.mkdir(parents=True, exist_ok=True)
                
                query_results_data = {
                    "original_text": text_content,
                    "query": query,
                    "results": [{"content": item.get("content", ""), "score": item.get("score", 0.0)} for item in result.results]
                }
                
                with open(query_folder / "01_search_results.json", 'w', encoding='utf-8') as f:
                    json.dump(query_results_data, f, ensure_ascii=False, indent=2)
                
                extracted_data = {"query": query, "relevant_contents": relevant_content_map.get(query, [])}
                
                with open(query_folder / "02_relevant_content.json", 'w', encoding='utf-8') as f:
                    json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved {len(results)} query folders in session: {session_id}")
            
        except Exception as e:
            logger.error(f"Error saving query logs: {e}")

    async def process_text_with_vietnamese_query_module(self, text_content: str) -> str:
        """
        Process general text content with Vietnamese Query Module and generate comprehensive response
        
        Args:
            text_content: Input text content to process
            
        Returns:
            str: Comprehensive response with information and sources
        """
        # Generate unique session ID for this processing session
        session_id = f"query_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        try:
            if self.query_module is None:
                self._init_query_module()
            
            logger.info(f"Processing text with Vietnamese Query Module - Session: {session_id}")
            results, conversation = self.query_module.process_text(text_content)
            
            if not results:
                logger.warning("No results from Vietnamese Query Module for text")
                return "Không tìm thấy thông tin liên quan đến nội dung của bạn."
            
            # Validate conversation context
            if not conversation:
                logger.error("No conversation context available from query module")
                return "Lỗi: Không có context cuộc hội thoại để xử lý văn bản."
            
            logger.info(f"Successfully obtained conversation context and {len(results)} query results. Generating final response...")

            # Step 1: Filtering & Extraction
            retrieved_info = ""
            content_evaluation_tasks = []

            all_queries = [r.original_query for r in results]
            
            for result in results:
                query = result.original_query
                if result.results:
                    for item in result.results:
                        content = item.get("content", "")
                        if content:
                            task = self._evaluate_and_extract_relevant_content(all_queries, content)
                            content_evaluation_tasks.append((query, item, task))
            
            content_evaluation_data = []
            if content_evaluation_tasks:
                logger.info(f"Extracting 'Core Snippets' from {len(content_evaluation_tasks)} retrieved chunks...")
                evaluation_results = await asyncio.gather(*(task for _, _, task in content_evaluation_tasks))
                logger.info("Extraction complete.")

                for (query, chunk, task), extraction_result in zip(content_evaluation_tasks, evaluation_results):
                    # Store for logging
                    content_evaluation_data.append((query, chunk, extraction_result))
                    
                    if extraction_result["is_relevant"]:
                        metadata = chunk.get("metadata", {})
                        file_created_at = metadata.get("file_created_at")
                        source = metadata.get("source")

                        retrieved_info += f"### Thông tin liên quan đến câu hỏi: \"{query}\"\n\n"
                        retrieved_info += f"**Trích xuất từ tài liệu:**"
                        if source and not source.startswith("gmail_thread"):
                            retrieved_info += f" [Nguồn: {source}]"
                        if file_created_at:
                            retrieved_info += f" (Cập nhật: {file_created_at})"
                        retrieved_info += f"\n---\n{extraction_result['relevant_content']}\n---\n\n"

            if not retrieved_info:
                retrieved_info = "Hệ thống không tìm thấy thông tin cụ thể nào sau khi chắt lọc."

            # Step 2: Synthesis & Response
            final_prompt = f"""
<instructions>
**VAI TRÒ:**
Bạn là một trợ lý AI chuyên gia, có nhiệm vụ tổng hợp thông tin từ các đoạn trích đã được chắt lọc và soạn một câu trả lời cuối cùng, mạch lạc, đầy đủ cho người dùng.

**BỐI CẢNH:**
Người dùng đã đưa ra một yêu cầu/câu hỏi. Hệ thống đã tìm kiếm và sau đó chắt lọc để lấy ra những **đoạn trích cốt lõi** liên quan nhất dưới đây. Các đoạn trích có thể có thông tin nguồn `[Nguồn: ...]` và ngày cập nhật `(Cập nhật: ...)`.

**YÊU CẦU GỐC CỦA NGƯỜI DÙNG:**
---
{text_content}
---

**CÁC ĐOẠN TRÍCH CỐT LÕI ĐÃ ĐƯỢC CHẮT LỌC:**
---
{retrieved_info}
---

**NHIỆM VỤ:**
Dựa trên **YÊU CẦU GỐC** và các **ĐOẠN TRÍCH CỐT LÕI**, hãy soạn một câu trả lời hoàn chỉnh, duy nhất.

**QUY TẮC SOẠN THẢO (TUÂN THỦ TUYỆT ĐỐI):**

1.  **Ưu tiên thông tin mới nhất (CỰC KỲ QUAN TRỌNG):**
    -   Nếu nhiều đoạn trích nói về cùng một chủ đề, bạn **BẮT BUỘC CHỈ SỬ DỤNG** thông tin từ đoạn trích có ngày cập nhật **MỚI NHẤT**.
    -   **TUYỆT ĐỐI KHÔNG** sử dụng hay trích dẫn thông tin từ các nguồn cũ hơn nếu nguồn mới nhất đã đủ để trả lời. Ví dụ: nếu có thông tin từ năm 2025 và 2023, chỉ dùng thông tin năm 2025.

2.  **Định dạng đầu ra (BẮT BUỘC):**
    -   Toàn bộ câu trả lời phải là **văn bản thuần (plain text)**.
    -   **KHÔNG ĐƯỢC PHÉP** sử dụng bất kỳ định dạng Markdown nào (ví dụ: không dùng `**` để in đậm, không dùng `*` hay `-` hay số để tạo danh sách). Viết thành các đoạn văn bình thường.

3.  **Trích dẫn nguồn:**
    -   Khi sử dụng thông tin từ một đoạn trích, hãy đặt footnote dạng số (ví dụ: `...nội dung [1].`). Nếu cùng nguồn thì sẽ cùng footnote.
    -   Tạo một mục `NGUỒN THAM KHẢO:` ở cuối câu trả lời.
    -   Trong mục này, liệt kê tất cả các nguồn đã được trích dẫn. Mỗi nguồn phải bao gồm **toàn bộ link/tên nguồn** được cung cấp trong phần `[Nguồn: ...]` của đoạn trích.

4.  **Cấu trúc và giọng văn:**
    -   Mở đầu ngắn gọn, đi thẳng vào vấn đề.
    -   Tổng hợp thông tin một cách mạch lạc để trả lời yêu cầu của người dùng.
    -   Giọng văn chuyên nghiệp, rõ ràng.
    -   Nếu không có thông tin để trả lời phần nào đó, hãy trung thực nêu rõ: "Hiện tại hệ thống chưa có thông tin chi tiết về...".

Viết câu trả lời cuối cùng ngay dưới đây, tuân thủ nghiêm ngặt tất cả các quy tắc trên.
</instructions>
"""

            final_response = "Có lỗi xảy ra khi tạo phản hồi."
            deepseek_client = self._get_deepseek_client()
            if conversation and deepseek_client:
                try:
                    final_response = deepseek_client.send_message(
                        conversation=conversation,
                        message=final_prompt,
                        temperature=0.3,
                        max_tokens=8192,
                        error_default="Có lỗi xảy ra khi tạo phản hồi."
                    )
                except Exception as e:
                    logger.error(f"Error in conversation-based response generation: {e}")
                    final_response = "Xin lỗi, có lỗi xảy ra trong quá trình tạo phản hồi. Vui lòng thử lại sau."
            else:
                logger.error("No conversation context available for response generation")
                final_response = "Không có context cuộc hội thoại để tạo phản hồi."
            
            # Save logs
            self._save_query_processing_log(text_content, results, content_evaluation_data, final_response, session_id)
            
            return final_response
            
        except Exception as e:
            logger.warning(f"Error processing text with Vietnamese Query Module: {e}")
            return "Xin lỗi, có lỗi xảy ra khi xử lý văn bản. Vui lòng thử lại sau."

    async def _evaluate_and_extract_relevant_content(self, all_queries: List[str], chunk_content: str) -> Dict[str, Any]:
        deepseek_client = self._get_deepseek_client()
        if not all_queries or not chunk_content or not deepseek_client:
            return {"is_relevant": False, "relevant_content": ""}

        try:
            system_message = "Bạn là một AI chuyên gia đánh giá và trích xuất thông tin, hoạt động như một bộ lọc chất lượng trong hệ thống RAG."
            
            queries_str = "\n".join(f"- {q}" for q in all_queries)

            user_message = f"""
<instructions>
**VAI TRÒ:**
Bạn là một AI chuyên gia đánh giá và trích xuất thông tin, hoạt động như một bộ lọc chất lượng cao trong hệ thống RAG.

**NHIỆM VỤ:**
Bạn sẽ nhận được một **DANH SÁCH CÁC CÂU HỎI GỐC** và một **VĂN BẢN**. Nhiệm vụ của bạn là đánh giá xem văn bản này có liên quan đến **BẤT KỲ CÂU HỎI NÀO** trong danh sách không, và nếu có, hãy trích xuất thông tin hữu ích nhất.

**QUY TRÌNH THỰC HIỆN:**
1.  **Đánh giá mức độ liên quan:** Đọc kỹ danh sách câu hỏi và văn bản. Quyết định xem văn bản này có chứa thông tin hữu ích để trả lời **ít nhất một** trong các câu hỏi không. Thông tin không nhất thiết phải là câu trả lời trực tiếp, mà có thể là thông tin nền, giải thích, hoặc các chi tiết liên quan giúp làm sáng tỏ câu hỏi.
2.  **Trích xuất thông tin:**
    *   **Nếu văn bản có liên quan đến bất kỳ câu hỏi nào:** Hãy trích xuất một **đoạn trích cốt lõi**. Đoạn trích này nên mạch lạc, đầy đủ và chứa tất cả thông tin trong văn bản giúp trả lời (các) câu hỏi liên quan một cách toàn diện. Thay vì chỉ lấy một câu trả lời ngắn gọn, hãy bao gồm cả ngữ cảnh xung quanh để người đọc hiểu rõ vấn đề. Đoạn trích phải được giữ nguyên văn từ văn bản gốc.
    *   **Nếu văn bản không liên quan:** Trả về một chuỗi rỗng cho nội dung trích xuất.
3.  **Định dạng đầu ra:** Trả về kết quả dưới dạng một đối tượng JSON duy nhất.

**DANH SÁCH CÁC CÂU HỎI GỐC:**
---
{queries_str}
---

**VĂN BẢN CẦN ĐÁNH GIÁ VÀ TRÍCH XUẤT:**
---
{chunk_content}
---

**ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC):**
Chỉ trả về một đối tượng JSON hợp lệ với cấu trúc sau. Đảm bảo escape đúng tất cả ký tự đặc biệt:
```json
{{
  "is_relevant": <true nếu văn bản có liên quan, ngược lại false>,
  "relevant_content": "<nội dung được trích xuất nếu is_relevant là true, ngược lại là chuỗi rỗng>"
}}
```
</instructions>
"""
            
            response_text = await call_deepseek_async(
                deepseek_client=deepseek_client,
                system_message=system_message,
                user_message=user_message,
                temperature=0.0,
                max_tokens=4000,
                error_default='{"is_relevant": false, "relevant_content": ""}'
            )
                    
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error during C-RAG evaluation for query '{all_queries}': {e}")
            return {"is_relevant": False, "relevant_content": ""}

    def _search_multiple_collections(self, question: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Search in both main collection and EMAIL_QA collection using existing query module
        
        Args:
            question: The question to search for
            
        Returns:
            Tuple of (main_collection_results, email_qa_results)
        """
        if self.query_module is None:
            logger.warning("Query module not initialized")
            return [], []
        
        # Store original collection name
        original_collection = self.query_module.embedding_module.qdrant_manager.collection_name
        
        try:
            main_results = self.query_module.process_single_query(question)
            
            # Temporarily switch to EMAIL_QA collection
            self.query_module.embedding_module.qdrant_manager.collection_name = settings.EMAIL_QA_COLLECTION
            qa_results = self.query_module.process_single_query(question)
            
            logger.info(f"Found {len(main_results)} results in main collection and {len(qa_results)} results in EMAIL_QA collection for question: {question[:50]}...")
            
            return main_results, qa_results
            
        except Exception as e:
            logger.error(f"Error searching multiple collections: {e}")
            return [], []
        finally:
            # Restore original collection name
            self.query_module.embedding_module.qdrant_manager.collection_name = original_collection

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
