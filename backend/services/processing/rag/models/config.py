"""
Configuration for LLM models in the RAG pipeline.
"""

import os
from typing import Dict, Any, Optional
from backend.core.config import settings

def get_model_config(model_type: str, custom_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get the configuration for a specific model type.
    
    Args:
        model_type (str): Type of model (openai, deepseek, gemini)
        custom_config (dict, optional): Custom configuration to override defaults
        
    Returns:
        dict: Model configuration
    """
    # Default configurations
    default_configs = {
        "openai": {
            "api_key": settings.OPENAI_API_KEY if hasattr(settings, "OPENAI_API_KEY") else "",
            "model_name": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 1024
        },
        "deepseek": {
            "api_key": settings.DEEPSEEK_API_KEY,
            "model_name": settings.DEEPSEEK_MODEL,
            "temperature": 0.7,
            "max_tokens": 1024
        },
        "gemini": {
            "api_key": settings.GEMINI_API_KEY if hasattr(settings, "GEMINI_API_KEY") else "",
            "model_name": "gemini-pro",
            "temperature": 0.7,
            "max_tokens": 1024
        }
    }
    
    # Get default config for the model type
    if model_type not in default_configs:
        raise ValueError(f"Unsupported model type: {model_type}")
        
    config = default_configs[model_type].copy()
    
    # Override with custom config if provided
    if custom_config:
        config.update(custom_config)
        
    return config 