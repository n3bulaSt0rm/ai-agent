"""
LLM Models for RAG Pipeline

This package contains different LLM implementations for the RAG pipeline.
"""

from backend.services.processing.rag.models.base_model import BaseModel
from backend.services.processing.rag.models.openai.main import OpenAIModel
from backend.services.processing.rag.models.deepseek.main import DeepSeekModel
from backend.services.processing.rag.models.gemini.main import GeminiModel
from backend.services.processing.rag.models.config import get_model_config

def create_openai_model(config=None):
    """
    Create an OpenAI model with the given configuration.
    
    Args:
        config (dict, optional): Custom configuration
        
    Returns:
        OpenAIModel: Initialized OpenAI model
    """
    model_config = get_model_config("openai", config)
    
    return OpenAIModel(
        api_key=model_config["api_key"],
        model_name=model_config["model_name"],
        temperature=model_config["temperature"],
        max_tokens=model_config["max_tokens"]
    )

def create_deepseek_model(config=None):
    """
    Create a DeepSeek model with the given configuration.
    
    Args:
        config (dict, optional): Custom configuration
        
    Returns:
        DeepSeekModel: Initialized DeepSeek model
    """
    model_config = get_model_config("deepseek", config)
    
    return DeepSeekModel(
        api_key=model_config["api_key"],
        model_name=model_config["model_name"],
        temperature=model_config["temperature"],
        max_tokens=model_config["max_tokens"]
    )

def create_gemini_model(config=None):
    """
    Create a Gemini model with the given configuration.
    
    Args:
        config (dict, optional): Custom configuration
        
    Returns:
        GeminiModel: Initialized Gemini model
    """
    model_config = get_model_config("gemini", config)
    
    return GeminiModel(
        api_key=model_config["api_key"],
        model_name=model_config["model_name"],
        temperature=model_config["temperature"],
        max_tokens=model_config["max_tokens"]
    )

def create_model(model_type="openai", config=None):
    """
    Create a model of the specified type with the given configuration.
    
    Args:
        model_type (str): Type of model ("openai", "deepseek", "gemini")
        config (dict, optional): Configuration dictionary
        
    Returns:
        BaseModel: Initialized model
    """
    model_type = model_type.lower()
    
    if model_type == "openai":
        return create_openai_model(config)
    elif model_type == "deepseek":
        return create_deepseek_model(config)
    elif model_type == "gemini":
        return create_gemini_model(config)
    else:
        raise ValueError(f"Unsupported model type: {model_type}")

__all__ = [
    'BaseModel', 
    'OpenAIModel', 
    'DeepSeekModel', 
    'GeminiModel',
    'create_model',
    'create_openai_model',
    'create_deepseek_model',
    'create_gemini_model'
] 