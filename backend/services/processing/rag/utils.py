"""
Shared utilities for RAG processing services.
"""

import logging
import requests
import time
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