"""
RAG (Retrieval-Augmented Generation) handler for processing Gmail emails.
This module is responsible for:
1. Monitoring Gmail inbox for new emails
2. Extracting content from the emails
3. Querying Qdrant to find relevant information
4. Generating responses using DeepSeek API
5. Creating email draft responses
"""

import os
import base64
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail API
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Qdrant for vector search
from backend.db.vector_store import get_vector_store_async
from backend.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Define scope for Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 
          'https://www.googleapis.com/auth/gmail.compose']

class GmailHandler:
    """
    Handler for monitoring Gmail inbox, processing emails, and generating responses.
    """
    
    def __init__(self, credentials_path: str = None, 
                 token_path: str = None, poll_interval: int = None):
        """
        Initialize Gmail handler with authentication.
        
        Args:
            credentials_path: Path to the credentials JSON file
            token_path: Path to the token JSON file
            poll_interval: Interval in seconds between inbox checks
        """
        self.credentials_path = credentials_path or settings.GMAIL_CREDENTIALS_PATH
        self.token_path = token_path or settings.GMAIL_TOKEN_PATH
        self.service = None
        self.user_id = 'me'  # 'me' refers to the authenticated user
        
        # Poll interval in seconds
        self.poll_interval = poll_interval or settings.GMAIL_POLL_INTERVAL
        
        # Get DeepSeek API settings from config
        self.deepseek_api_key = settings.DEEPSEEK_API_KEY
        self.deepseek_api_url = settings.DEEPSEEK_API_URL
        self.deepseek_model = settings.DEEPSEEK_MODEL
        
        if not self.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY not set in settings")
            
    def authenticate(self) -> None:
        """
        Authenticate with Gmail API.
        
        Raises:
            FileNotFoundError: If credentials file doesn't exist
            Exception: If authentication fails
        """
        creds = None
        
        # Check if token file exists
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_info(
                    json.load(open(self.token_path)), SCOPES)
            except Exception as e:
                logger.error(f"Error loading token file: {e}")
                creds = None
                
        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}")
                    creds = None
            
            # If still no valid creds, need to do OAuth flow
            if not creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
                    
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error in OAuth flow: {e}")
                    raise
                
            # Save credentials for next time
            try:
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"Saved authentication token to {self.token_path}")
            except Exception as e:
                logger.error(f"Error saving token: {e}")
                
        # Build Gmail service
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Successfully authenticated with Gmail API")
        except Exception as e:
            logger.error(f"Error building Gmail service: {e}")
            raise
            
    async def fetch_unread_emails(self) -> List[Dict[str, Any]]:
        """
        Fetch unread emails from Gmail inbox.
        
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
            
    async def query_qdrant(self, query_text: str) -> List[Dict[str, Any]]:
        """
        Query Qdrant vector database for relevant documents.
        
        Args:
            query_text: Query text from email
            
        Returns:
            List of relevant documents
            
        Raises:
            Exception: If querying Qdrant fails
        """
        try:
            # Get vector store
            vector_store = await get_vector_store_async()
            
            # Search in vector store
            search_params = {
                "query_text": query_text,
                "limit": 5,  # Retrieve top 5 results
            }
            
            # Add filter for non-deleted documents if the vector store supports it
            if hasattr(vector_store, 'search') and 'filters' in vector_store.search.__code__.co_varnames:
                search_params["filters"] = {"is_deleted": False}
                
            results = await vector_store.search(**search_params)
            
            return results
        except Exception as e:
            logger.error(f"Error querying Qdrant: {e}")
            return []
            
    async def call_deepseek_api(self, user_query: str, context: List[Dict[str, Any]]) -> str:
        """
        Call DeepSeek API to generate email response.
        
        Args:
            user_query: User's query from email
            context: Relevant documents from Qdrant
            
        Returns:
            Generated email response
            
        Raises:
            Exception: If calling DeepSeek API fails
        """
        import httpx
        
        if not self.deepseek_api_key:
            logger.error("DeepSeek API key not set")
            return "Error: DeepSeek API key not configured"
            
        try:
            # Format context for the API
            formatted_context = ""
            for i, doc in enumerate(context):
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})
                
                # Add document information to context
                formatted_context += f"Document {i+1}:\n"
                if "file_id" in metadata:
                    formatted_context += f"File ID: {metadata['file_id']}\n"
                if "page" in metadata:
                    formatted_context += f"Page: {metadata['page']}\n"
                formatted_context += f"Content: {content}\n\n"
            
            # Prepare prompt for DeepSeek API
            prompt = f"""You are an AI assistant that drafts email responses based on user queries and available information.
            
User Query: {user_query}

Relevant Information:
{formatted_context}

Please draft a professional email response that addresses the user's query using the relevant information provided. The response should be clear, concise, and formatted as an email.
"""
            
            # Call DeepSeek API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.deepseek_api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.deepseek_api_key}"
                    },
                    json={
                        "model": self.deepseek_model,
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant that drafts emails."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000
                    },
                    timeout=30.0
                )
                
                response_data = response.json()
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    generated_text = response_data["choices"][0]["message"]["content"]
                    return generated_text
                else:
                    logger.error(f"Unexpected response format: {response_data}")
                    return "Error: Unexpected response format from DeepSeek API"
                    
        except Exception as e:
            logger.error(f"Error calling DeepSeek API: {e}")
            return f"Error generating response: {str(e)}"
            
    def create_draft_email(self, to: str, subject: str, body: str) -> None:
        """
        Create a draft email in Gmail.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body
            
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
            
            logger.info(f"Draft created with ID: {draft['id']}")
            
        except Exception as e:
            logger.error(f"Error creating draft: {e}")
            raise
            
    async def process_email(self, email: Dict[str, Any]) -> None:
        """
        Process a single email:
        1. Extract query from email body
        2. Query Qdrant for relevant documents
        3. Call DeepSeek API to generate response
        4. Create draft email response
        5. Mark original email as read
        
        Args:
            email: Email message details
            
        Raises:
            Exception: If processing fails
        """
        try:
            # Extract query from email body
            query = email['body'].strip()
            
            if not query:
                logger.warning(f"Empty query in email: {email['id']}")
                return
                
            logger.info(f"Processing query: {query[:100]}...")
            
            # Query Qdrant
            qdrant_results = await self.query_qdrant(query)
            
            if not qdrant_results:
                logger.warning("No relevant documents found in Qdrant")
                
            # Call DeepSeek API
            response_text = await self.call_deepseek_api(query, qdrant_results)
            
            # Create draft email
            self.create_draft_email(
                to=email['from'],
                subject=email['subject'],
                body=response_text
            )
            
            # Mark email as read
            self.mark_as_read(email['id'])
            
            logger.info(f"Successfully processed email {email['id']}")
            
        except Exception as e:
            logger.error(f"Error processing email: {e}")
            raise
            
    async def run(self) -> None:
        """
        Main loop to continuously monitor Gmail inbox.
        
        This method runs indefinitely, checking for new emails
        at regular intervals.
        """
        logger.info("Starting Gmail monitoring service")
        
        while True:
            try:
                # Authenticate if needed
                if not self.service:
                    self.authenticate()
                    
                # Fetch unread emails
                unread_emails = await self.fetch_unread_emails()
                
                if unread_emails:
                    logger.info(f"Found {len(unread_emails)} unread email(s)")
                    
                    # Process each email
                    for email in unread_emails:
                        await self.process_email(email)
                
                # Wait before checking again
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in Gmail monitor loop: {e}")
                # Wait before retrying
                await asyncio.sleep(self.poll_interval)
                
# Global instance for the handler
_gmail_handler = None

def get_gmail_handler() -> GmailHandler:
    """
    Get the Gmail handler instance (singleton pattern).
    
    Returns:
        GmailHandler instance
    """
    global _gmail_handler
    if _gmail_handler is None:
        _gmail_handler = GmailHandler()
    return _gmail_handler

async def start_gmail_handler() -> None:
    """
    Start the Gmail handler service.
    
    This function initializes and runs the Gmail handler.
    """
    try:
        handler = get_gmail_handler()
        await handler.run()
    except Exception as e:
        logger.error(f"Failed to start Gmail handler: {e}")
        
# Async task to hold the running handler
gmail_task = None

async def start_monitoring_async():
    """
    Start monitoring Gmail inbox in the background.
    
    Returns:
        Asyncio task running the handler
    """
    global gmail_task
    if gmail_task is None or gmail_task.done():
        gmail_task = asyncio.create_task(start_gmail_handler())
    return gmail_task
