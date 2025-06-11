"""
Shared utilities for RAG processing services.
"""

import logging
import requests
import time
import base64
from typing import Dict, Any, List, Optional

from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.exceptions import LangChainException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepSeekAPIClient:
    """LangChain-based DeepSeek API Client with conversation memory management"""
    
    def __init__(self, api_key: str, api_url: str = None, model: str = "deepseek-chat"):
        """
        Initialize DeepSeek client using LangChain ChatDeepSeek
        
        Args:
            api_key (str): DeepSeek API key
            api_url (str): API URL (ignored - LangChain handles this)
            model (str): Model name
        """
        if not api_key:
            raise ValueError("DeepSeek API key is required")
            
        self.api_key = api_key
        self.model = model
        
        self.llm = ChatDeepSeek(
            api_key=api_key,
            model=model,
            max_retries=3,
            timeout=240
        )
        
        logger.info(f"✓ DeepSeek LangChain client initialized for model: {model}")
    
    def start_conversation(self, system_message: str) -> InMemoryChatMessageHistory:
        try:
            # Create InMemoryChatMessageHistory instance
            memory = InMemoryChatMessageHistory()
            
            # Add system message to memory
            memory.add_message(SystemMessage(content=system_message))
            
            logger.debug(f"Started new conversation with system message")
            return memory
            
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            raise LangChainException(f"Failed to start conversation: {e}")
    
    def send_message(self, conversation: InMemoryChatMessageHistory, message: str, 
                     temperature: float = 0.5, max_tokens: int = 7000, 
                     error_default: str = None) -> str:
        if not conversation:
            error_msg = "Conversation memory is required"
            logger.error(error_msg)
            if error_default is None:
                raise ValueError(error_msg)
            return error_default
        
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                # Add user message to conversation
                conversation.add_message(HumanMessage(content=message))
                
                # Get all messages from memory
                messages = conversation.messages
                
                logger.debug(f"Calling DeepSeek with {len(messages)} messages (attempt {attempt + 1}/{max_retries})")
                
                response = self.llm.invoke(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                if hasattr(response, 'content') and response.content:
                    generated_text = response.content
                    
                    # Add AI response to conversation
                    conversation.add_message(AIMessage(content=generated_text))
                    
                    logger.debug(f"DeepSeek conversation message successful on attempt {attempt + 1}")
                    return generated_text
                else:
                    raise LangChainException("Empty response from DeepSeek")
                    
            except Exception as e:
                error_msg = f"DeepSeek API error (attempt {attempt + 1}/{max_retries}): {e}"
                logger.warning(error_msg)
                
                # For final attempt, handle error appropriately
                if attempt == max_retries - 1:
                    if error_default is None:
                        raise LangChainException(f"DeepSeek API failed after {max_retries} retries: {e}")
                    else:
                        return error_default
                
                # Wait before retrying (except on last attempt)
                if attempt < max_retries - 1:
                    logger.info(f"Retrying DeepSeek conversation message in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
        
        # If we reach here, all retries failed
        if error_default is None:
            raise LangChainException("DeepSeek API failed after all retries")
        return error_default
    
    def add_context_to_conversation(self, conversation: InMemoryChatMessageHistory, context: str):
        """
        Add context information to conversation memory
        
        Args:
            conversation (InMemoryChatMessageHistory): The conversation memory
            context (str): Context to add
        """
        try:
            if conversation and context:
                # Add context as a system message
                conversation.add_message(SystemMessage(content=f"Context: {context}"))
                logger.debug("Added context to conversation memory")
        except Exception as e:
            logger.warning(f"Error adding context to conversation: {e}")

def create_deepseek_client(deepseek_api_key: str, deepseek_api_url: str = None, 
                          deepseek_model: str = "deepseek-chat") -> DeepSeekAPIClient:
    """
    Create and return a DeepSeek API client using LangChain
    
    Args:
        deepseek_api_key (str): DeepSeek API key
        deepseek_api_url (str): API URL (ignored - LangChain handles this)
        deepseek_model (str): Model name
        
    Returns:
        DeepSeekAPIClient: Configured DeepSeek client
    """
    return DeepSeekAPIClient(
        api_key=deepseek_api_key,
        api_url=deepseek_api_url,
        model=deepseek_model
    )

def extract_image_attachments(gmail_service, user_id: str, payload: Dict, message_id: str) -> List[Dict[str, Any]]:
    """
    Extract image attachments from email payload - shared utility for handler and worker
    
    Args:
        gmail_service: Gmail API service object
        user_id: Gmail user ID
        payload: Email payload from Gmail API
        message_id: Gmail message ID for downloading external attachments
        
    Returns:
        List of image attachment data
    """
    attachments = []
    
    def process_part(part):
        """Recursively process email parts to find images"""
        mime_type = part.get('mimeType', '')
        filename = part.get('filename', '')
        
        logger.debug(f"Processing part: mimeType={mime_type}, filename={filename}")
        
        # Check if this part is an image
        if mime_type.startswith('image/'):
            logger.info(f"Found image part: {mime_type}, {filename}")
            attachment_data = get_attachment_data(gmail_service, user_id, part, message_id)
            if attachment_data:
                attachments.append(attachment_data)
                logger.info(f"Successfully extracted image: {attachment_data['filename']} ({attachment_data['size']} bytes)")
            else:
                logger.warning(f"Failed to extract image data for: {filename}")
        
        # Process nested parts
        if 'parts' in part:
            for subpart in part['parts']:
                process_part(subpart)
    
    # Start processing from the main payload
    if 'parts' in payload:
        for part in payload['parts']:
            process_part(part)
    else:
        # Single part email
        process_part(payload)
    
    logger.info(f"Found {len(attachments)} image attachments")
    return attachments

def get_attachment_data(gmail_service, user_id: str, part: Dict, message_id: str) -> Optional[Dict[str, Any]]:
    """
    Get attachment data from email part - shared utility
    
    Args:
        gmail_service: Gmail API service object
        user_id: Gmail user ID
        part: Email part containing attachment
        message_id: Gmail message ID for downloading external attachments
        
    Returns:
        Attachment data dictionary or None
    """
    try:
        body = part.get('body', {})
        attachment_id = body.get('attachmentId')
        
        if not attachment_id:
            # Inline attachment
            data = body.get('data')
            if data:
                image_data = base64.urlsafe_b64decode(data)
                
                filename = part.get('filename', 'inline_image')
                mime_type = part.get('mimeType', 'image/jpeg')
                
                return {
                    'data': image_data,
                    'filename': filename,
                    'mime_type': mime_type,
                    'size': len(image_data)
                }
        else:
            # External attachment - download it
            try:
                attachment = gmail_service.users().messages().attachments().get(
                    userId=user_id,
                    messageId=message_id,
                    id=attachment_id
                ).execute()
                
                data = attachment.get('data')
                if data:
                    image_data = base64.urlsafe_b64decode(data)
                    
                    filename = part.get('filename', 'attachment_image')
                    mime_type = part.get('mimeType', 'image/jpeg')
                    
                    logger.info(f"Downloaded external attachment: {filename} ({len(image_data)} bytes)")
                    
                    return {
                        'data': image_data,
                        'filename': filename,
                        'mime_type': mime_type,
                        'size': len(image_data)
                    }
            except Exception as e:
                logger.error(f"Error downloading external attachment {attachment_id}: {e}")
                return None
        
    except Exception as e:
        logger.error(f"Error getting attachment data: {e}")
        return None

def extract_text_content(payload: Dict) -> str:
    """
    Extract text content from email payload - shared utility
    
    Args:
        payload: Email payload from Gmail API
        
    Returns:
        Extracted text content
    """
    body_text = ""
    
    def extract_text_from_part(part):
        nonlocal body_text
        mime_type = part.get('mimeType', '')
        body = part.get('body', {})
        
        if mime_type == 'text/plain':
            data = body.get('data', '')
            if data:
                decoded_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                body_text += decoded_text + "\n"
        
        elif mime_type == 'text/html':
            data = body.get('data', '')
            if data:
                html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                # Convert HTML to plain text (basic implementation)
                import re
                text = re.sub('<[^<]+?>', '', html_content)
                text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                body_text += text + "\n"
        
        # Process nested parts
        if 'parts' in part:
            for subpart in part['parts']:
                extract_text_from_part(subpart)
    
    # Extract text from all parts
    if 'parts' in payload:
        for part in payload['parts']:
            extract_text_from_part(part)
    else:
        # Single part email
        extract_text_from_part(payload)
    
    return body_text.strip()

def extract_all_attachments(gmail_service, user_id: str, payload: Dict, message_id: str) -> List[Dict[str, Any]]:
    """
    Extract all attachments (images and PDFs) from email payload - shared utility for handler and worker
    
    Args:
        gmail_service: Gmail API service object
        user_id: Gmail user ID
        payload: Email payload from Gmail API
        message_id: Gmail message ID for downloading external attachments
        
    Returns:
        List of attachment data with type indicators
    """
    attachments = []
    
    def process_part(part):
        """Recursively process email parts to find attachments"""
        mime_type = part.get('mimeType', '')
        filename = part.get('filename', '')
        
        logger.debug(f"Processing part: mimeType={mime_type}, filename={filename}")
        
        # Check if this part is an image or PDF
        if mime_type.startswith('image/') or mime_type == 'application/pdf':
            logger.info(f"Found attachment part: {mime_type}, {filename}")
            attachment_data = get_attachment_data(gmail_service, user_id, part, message_id)
            if attachment_data:
                # Add attachment type for easier processing
                if mime_type.startswith('image/'):
                    attachment_data['attachment_type'] = 'image'
                elif mime_type == 'application/pdf':
                    attachment_data['attachment_type'] = 'pdf'
                
                attachments.append(attachment_data)
                logger.info(f"Successfully extracted {attachment_data['attachment_type']}: {attachment_data['filename']} ({attachment_data['size']} bytes)")
            else:
                logger.warning(f"Failed to extract attachment data for: {filename}")
        
        # Process nested parts
        if 'parts' in part:
            for subpart in part['parts']:
                process_part(subpart)
    
    # Start processing from the main payload
    if 'parts' in payload:
        for part in payload['parts']:
            process_part(part)
    else:
        # Single part email
        process_part(payload)
    
    logger.info(f"Found {len(attachments)} attachments (images and PDFs)")
    return attachments

def save_attachment_to_temp_file(attachment_data: Dict[str, Any]) -> str:
    """
    Save attachment data to a temporary file and return the file path
    
    Args:
        attachment_data: Dictionary containing attachment data with 'data', 'filename', 'mime_type'
        
    Returns:
        Path to temporary file
    """
    import tempfile
    import os
    
    try:
        # Determine file extension
        filename = attachment_data.get('filename', 'attachment')
        mime_type = attachment_data.get('mime_type', '')
        
        if mime_type == 'application/pdf':
            suffix = '.pdf'
        elif mime_type.startswith('image/'):
            suffix = '.jpg' if 'jpeg' in mime_type else '.png'
        else:
            # Get extension from filename if available
            _, ext = os.path.splitext(filename)
            suffix = ext if ext else '.bin'
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(attachment_data['data'])
            temp_path = tmp_file.name
        
        logger.info(f"Saved attachment to temporary file: {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Error saving attachment to temp file: {e}")
        raise 