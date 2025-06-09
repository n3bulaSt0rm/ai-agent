import os
import base64
import json
import asyncio
import logging
import time
from datetime import datetime, time as datetime_time
from typing import Dict, Any, List, Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import Vietnamese Query Module
from backend.services.processing.rag.retrievers.qdrant_retriever import VietnameseQueryModule, create_query_module
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.core.config import settings
from backend.db.metadata import get_metadata_db

from backend.services.processing.rag.draft_monitor import EmailDraftMonitor

from backend.services.processing.rag.utils import create_deepseek_client, DeepSeekAPIClient

# Configure logging
logger = logging.getLogger(__name__)

class GmailHandler:
    """
    Handler for monitoring Gmail inbox, processing emails, and generating responses.
    """
    
    def __init__(self, token_path: str = None, poll_interval: int = None):
        """
        Initialize Gmail handler with authentication.
        
        Args:
            token_path: Path to the token JSON file
            poll_interval: Interval in seconds between inbox checks
        """
        self.token_path = token_path or settings.GMAIL_TOKEN_PATH
        self.service = None
        self.user_id = 'me'  # 'me' refers to the authenticated user
        
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
        
        if settings.GMAIL_TOKEN_PATH:
            from backend.services.processing.rag.gmail_api_monitor import create_gmail_api_monitor
            # Use polling interval from settings
            self.api_monitor = create_gmail_api_monitor(gmail_handler=self, poll_interval=settings.GMAIL_POLL_INTERVAL)
        else:
            logger.error("Gmail API configuration missing. Ensure GMAIL_TOKEN_PATH exists")
            raise ValueError("Gmail API OAuth configuration required")
        
        logger.info("Draft monitor and Gmail API monitor initialized successfully")

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
                if hasattr(modules, 'cuda_memory_manager'):
                    memory_manager = modules.cuda_memory_manager
                    logger.info("Using shared CUDA Memory Manager from server")
                if hasattr(modules, 'embedding_module') and modules.embedding_module:
                    embedding_module = modules.embedding_module
                    logger.info("Using shared Embedding Module from server")
            except ImportError:
                logger.warning("Could not import modules from server")
            
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
            
            logger.info(f"Vietnamese Query Module initialized successfully with hybrid search and reranking")
            
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
            
    async def fetch_unread_emails(self) -> List[Dict[str, Any]]:
        """
        Fetch unread emails from Gmail inbox and process them.
        
        Returns:
            List of unread email messages
            
        Raises:
            Exception: If fetching emails fails
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
                
            # Fetch details for each message
            email_details = []
            for message in messages:
                msg = self.service.users().messages().get(
                    userId=self.user_id, 
                    id=message['id']).execute()
                    
                # Extract headers
                headers = {header['name']: header['value'] 
                          for header in msg['payload']['headers']}
                
                # Extract body
                body = self._get_email_body(msg)
                
                email_details.append({
                    'id': message['id'],
                    'threadId': msg['threadId'],
                    'from': headers.get('From', ''),
                    'to': headers.get('To', ''),
                    'subject': headers.get('Subject', ''),
                    'date': headers.get('Date', ''),
                    'body': body
                })
            
            if email_details:
                logger.info(f"Fetched {len(email_details)} unread emails, processing...")
                await self._group_and_process_emails(email_details)
            
            return email_details
            
        except HttpError as e:
            logger.error(f"Error fetching emails: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return []
            
    def _get_email_body(self, message: Dict[str, Any]) -> str:
        """
        Extract email body from Gmail message.
        
        Args:
            message: Gmail message object
            
        Returns:
            Email body text
        """
        body = ""
        
        try:
            if 'parts' in message['payload']:
                # Multipart message
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        if 'data' in part['body']:
                            body = base64.urlsafe_b64decode(
                                part['body']['data']).decode('utf-8')
                            break
            elif 'body' in message['payload'] and 'data' in message['payload']['body']:
                # Simple message
                body = base64.urlsafe_b64decode(
                    message['payload']['body']['data']).decode('utf-8')
        except Exception as e:
            logger.error(f"Error extracting email body: {e}")
                
        return body
        
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
            

    async def create_draft_email(self, to: str, subject: str, body: str, thread_id: str = None) -> str:
        """
        Create a draft email in Gmail.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            thread_id: Thread ID for tracking
            
        Returns:
            Draft ID if successful, None if failed
            
        Raises:
            Exception: If creating draft fails
        """
        try:
            # Create message
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = f"Re: {subject}"
            
            # Attach text part
            msg = MIMEText(body)
            message.attach(msg)
            
            # Encode message
            encoded_message = base64.urlsafe_b64encode(
                message.as_bytes()).decode()
                
            # Create draft
            draft = self.service.users().drafts().create(
                userId=self.user_id,
                body={'message': {'raw': encoded_message}}
            ).execute()
            
            draft_id = draft['id']
            
            logger.info(f"Draft created with ID: {draft_id}")
            return draft_id
            
        except Exception as e:
            logger.error(f"Error creating draft: {e}")
            raise
            
    def process_email_with_vietnamese_query_module(self, email_body: str) -> tuple[str, str]:
        try:
            if self.query_module is None:
                self._init_query_module()
            
            logger.info("Processing email with Vietnamese Query Module")
            results, conversation = self.query_module.process_email(email_body)
            
            if not results:
                logger.warning("No results from Vietnamese Query Module")
                return "Không tìm thấy thông tin liên quan đến câu hỏi của bạn.", "Email không có thông tin liên quan"
            
            # Validate conversation context
            if not conversation:
                logger.error("No conversation context available from query module")
                return "Lỗi: Không có context cuộc hội thoại để xử lý email.", "Lỗi conversation context"
            
            logger.info(f"Successfully obtained conversation context and {len(results)} query results")
            context_summary = results[0].context_summary if results else "Tóm tắt email lỗi"
            
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
                            
                            group_info += f"Tài liệu {k+1}:"
                            if file_created_at:
                                group_info += f" (Cập nhật: {file_created_at})"
                            group_info += f"\n{content}\n\n"
                    else:
                        group_info += f"Câu hỏi {j+1}: {query}\nKhông tìm thấy thông tin liên quan.\n\n"
                
                summarization_prompt = f"""
                Hãy tóm tắt lại các nội dung liên quan đến các câu hỏi và context sau một cách chính xác, đầy đủ thông tin, súc tích:
                Context: {email_body}
                
                Các câu hỏi: {', '.join(group_queries)}
                
                Thông tin liên quan:
                {group_info}
                
                LƯU Ý QUAN TRỌNG:
                - Nếu có nhiều tài liệu về cùng một chủ đề với các ngày cập nhật khác nhau, chỉ sử dụng thông tin từ tài liệu có ngày cập nhật mới nhất.
                - Khi sử dụng thông tin từ tài liệu có ngày cập nhật, hãy ghi rõ ngày cập nhật đó trong tóm tắt (ví dụ: "Theo thông tin cập nhật ngày 15/03/2024, thủ tục làm bằng tốt nghiệp yêu cầu...").
                - Đối với thông tin chỉ có một tài liệu hoặc không có ngày cập nhật rõ ràng, không cần ghi ngày cập nhật.
                - Đảm bảo tóm tắt bao gồm thông tin cập nhật nhất về từng vấn đề.
                """
                
                # Use conversation memory only to maintain context
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
            
            email_prompt = f"""Bạn là một trợ lý AI hỗ trợ phòng công tác sinh viên trong việc trả lời email.
Dưới đây là nội dung email từ sinh viên:

{email_body}

Dựa trên nội dung email và thông tin tìm thấy, hãy soạn một email phản hồi:
"""
            for i, summary in enumerate(summarized_results):
                email_prompt += f"Nhóm thông tin {i+1}: {summary['summary']}\n"
            
            email_prompt += """
Dựa trên các thông tin trên, hãy soạn một email phản hồi:
- Trình bày bằng tiếng Việt chuẩn, đúng chính tả, dễ hiểu.
- ĐẶC BIỆT QUAN TRỌNG: Viết email dưới dạng văn bản thuần (plain text), KHÔNG sử dụng markdown format hay bất kỳ định dạng nào khác.
- Trả lời lần lượt từng câu hỏi, dựa vào thông tin đã tóm tắt.
- ĐẶC BIỆT QUAN TRỌNG: Nếu biết thông tin được cập nhật vào ngày nào (có ngày cập nhật cụ thể), hãy ghi rõ ngày cập nhật đó trong câu trả lời để người dùng biết đây là thông tin mới nhất. Ví dụ: "Theo thông tin cập nhật ngày 15/03/2024, quy trình đăng ký học phần đã thay đổi..."
- Đối với các thông tin không có ngày cập nhật cụ thể, trả lời bình thường không cần ghi ngày.
- Nếu không có đủ thông tin, hãy đề xuất người gửi liên hệ bộ phận có thẩm quyền hoặc cung cấp thêm chi tiết.
- Đảm bảo định dạng email hành chính: lời chào, nội dung chính, lời kết, ký tên.

Viết email phản hồi ngay dưới đây (chỉ trả về nội dung email thuần(plain text)):
"""
            
            # Use conversation memory only for final email generation to maintain context
            if conversation and self.deepseek_client:
                try:
                    email_response = self.deepseek_client.send_message(
                        conversation=conversation,
                        message=email_prompt,
                        temperature=0.5,
                        max_tokens=4000,
                        error_default="Có lỗi xảy ra khi tạo email phản hồi."
                    )
                except Exception as e:
                    logger.error(f"Error in conversation-based email generation: {e}")
                    email_response = "Xin lỗi, có lỗi xảy ra trong quá trình tạo email phản hồi. Vui lòng thử lại sau."
            else:
                logger.error("No conversation context available for email generation")
                email_response = "Không có context cuộc hội thoại để tạo email phản hồi."
            
            return email_response, context_summary
            
        except Exception as e:
            logger.warning(f"Error processing email with Vietnamese Query Module: {e}")
            return "Xin lỗi, có lỗi xảy ra khi xử lý email. Vui lòng liên hệ trực tiếp để được hỗ trợ.", "Lỗi xử lý email"
    


    async def _group_and_process_emails(self, unread_emails: List[Dict[str, Any]]) -> None:
        if not unread_emails:
            return
            
        thread_emails = {}
        for email in unread_emails:
            thread_id = email['threadId']
            if thread_id not in thread_emails:
                thread_emails[thread_id] = []
            thread_emails[thread_id].append(email)
        
        for thread_id, emails in thread_emails.items():
            logger.info(f"Processing thread {thread_id} with {len(emails)} email(s)")
            await self.process_thread_with_context(thread_id, emails)

    async def process_thread_with_context(self, thread_id: str, unread_emails: List[Dict[str, Any]]) -> None:
        existing_draft_id = self.draft_monitor.check_existing_draft(thread_id)
        if existing_draft_id:
            logger.info(f"Thread {thread_id} has existing draft {existing_draft_id}, deleting")
            self.draft_monitor.delete_draft(existing_draft_id)
        
        thread_info = self.metadata_db.get_gmail_thread_info(thread_id)
        
        context_parts = []
        
        if thread_info and thread_info.get('context_summary'):
            context_parts.append(f"=== CONTEXT TỪ CUỘC HỘI THOẠI TRƯỚC ===\n{thread_info['context_summary']}\n")
        
        recent_responses = await self._fetch_responses_since_last_processed(
            thread_id, thread_info.get('last_processed_message_id') if thread_info else None
        )
        
        if recent_responses:
            context_parts.append("=== LỊCH SỬ TƯƠNG TÁC GẦN ĐÂY ===\n")
            for i, response in enumerate(recent_responses, 1):
                context_parts.append(f"Từ: {response['from']}\n")
                context_parts.append(f"Tiêu đề: {response['subject']}\n")
                context_parts.append(f"Nội dung: {response['body']}\n\n")
            context_parts.append("\n")
        
        context_parts.append("=== EMAIL CHƯA ĐỌC CẦN XỬ LÝ ===\n")
        for i, email in enumerate(unread_emails, 1):
            context_parts.append(f"Từ: {email['from']}\n")
            context_parts.append(f"Tiêu đề: {email['subject']}\n")
            context_parts.append(f"Nội dung: {email['body']}\n\n")
        
        full_context = "".join(context_parts)
        
        if not full_context.strip():
            logger.warning(f"Empty context for thread {thread_id}")
            return
        
        logger.info(f"Processing thread {thread_id} with comprehensive context")
        response_text, context_summary = self.process_email_with_vietnamese_query_module(full_context)
        
        newest_email = unread_emails[-1]
            
        to_address = newest_email['from']
        newest_subject = newest_email['subject']
        
        try:
            draft_id = await self.create_draft_email(
                to=to_address,
                subject=newest_subject,
                body=response_text,
                thread_id=thread_id
            )
            
            if draft_id:
                last_message_id = newest_email['id']
                self.metadata_db.upsert_gmail_thread(
                    thread_id=thread_id,
                    context_summary=context_summary,
                    current_draft_id=draft_id,
                    last_processed_message_id=last_message_id
                )
                
                marked_count = 0
                for email in unread_emails:
                    try:
                        self.mark_as_read(email['id'])
                        marked_count += 1
                    except Exception as mark_error:
                        logger.error(f"Failed to mark email {email['id']} as read: {mark_error}")
                
                logger.info(f"Successfully processed thread {thread_id}, draft ID: {draft_id}, marked {marked_count}/{len(unread_emails)} emails as read")
            else:
                logger.error(f"Failed to create draft for thread {thread_id}")
                
        except Exception as e:
            logger.error(f"Draft creation failed for thread {thread_id}: {e}")
            raise

    async def _fetch_responses_since_last_processed(self, thread_id: str, last_processed_message_id: str = None) -> List[Dict[str, Any]]:
        try:
            thread_messages = self.service.users().threads().get(
                userId=self.user_id, 
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread_messages.get('messages', [])
            admin_responses = []
            
            # If no last processed message ID, don't include any history
            if last_processed_message_id is None:
                logger.debug(f"No last processed message ID for thread {thread_id}, skipping history")
                return []
            
            found_last_processed = False
            
            for message in messages:
                if message['id'] == last_processed_message_id:
                    found_last_processed = True
                    continue  # Skip the last processed message itself
                
                if not found_last_processed:
                    continue  # Haven't found the starting point yet
                
                headers = {h['name']: h['value'] for h in message['payload']['headers']}
                message_from = headers.get('From', '')
                body = self._get_email_body(message)
                
                if body.strip():
                    admin_responses.append({
                        'id': message['id'],
                        'from': message_from,
                        'date': headers.get('Date', ''),
                        'body': body
                    })
            
            # If we never found the last processed message, it might have been deleted
            if not found_last_processed and last_processed_message_id:
                logger.warning(f"Last processed message {last_processed_message_id} not found in thread {thread_id}")
                # Return limited recent messages to avoid overwhelming context
                for message in messages[-5:]:  # Only last 5 messages
                    headers = {h['name']: h['value'] for h in message['payload']['headers']}
                    message_from = headers.get('From', '')
                    body = self._get_email_body(message)
                    
                    if body.strip():
                        admin_responses.append({
                            'id': message['id'],
                            'from': message_from,
                            'date': headers.get('Date', ''),
                            'body': body
                        })
            
            logger.info(f"Found {len(admin_responses)} messages for thread {thread_id}")
            return admin_responses
            
        except Exception as e:
            logger.error(f"Error fetching responses for thread {thread_id}: {e}")
            return []

    async def run(self) -> None:
        
        if not self.service:
            self.authenticate()
            
        if not self.draft_monitor or not self.api_monitor:
            self._initialize_managers()
        
        logger.info("Starting Gmail monitoring with API polling")
        
        await self.api_monitor.start_monitoring()
        logger.info("Gmail API polling monitoring started")
                
async def start_gmail_monitoring():
    handler = GmailHandler()
    await handler.run()
