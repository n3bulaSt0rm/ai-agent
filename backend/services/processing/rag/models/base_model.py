"""
Base Model for LLM implementations
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

class BaseModel:
    """Base class for LLM models."""
    
    def __init__(self, 
                api_key: str,
                model_name: str,
                temperature: float = 0.7,
                max_tokens: int = 1024):
        """
        Initialize the model.
        
        Args:
            api_key (str): API key for the model
            model_name (str): Name of the model
            temperature (float): Temperature for generation
            max_tokens (int): Maximum number of tokens to generate
        """
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    def generate_answer(self, query: str, context: str) -> str:
        """
        Generate an answer for a question with context.
        
        Args:
            query (str): The question
            context (str): The context
            
        Returns:
            str: The generated answer
        """
        raise NotImplementedError("Subclasses must implement this method") 