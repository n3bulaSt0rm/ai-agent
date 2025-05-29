"""
Shared Configuration for All LLM Models
"""

# OpenAI model configuration
OPENAI_CONFIG = {
    "api_key": "",
    "model_name": "gpt-3.5-turbo",
    "temperature": 0.7,
    "max_tokens": 1024
}

# DeepSeek model configuration
DEEPSEEK_CONFIG = {
    "api_key": "",
    "model_name": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 1024
}

# Gemini model configuration
GEMINI_CONFIG = {
    "api_key": "",
    "model_name": "gemini-pro",
    "temperature": 0.7,
    "max_tokens": 1024
}

# Default configuration by model type
DEFAULT_CONFIGS = {
    "openai": OPENAI_CONFIG,
    "deepseek": DEEPSEEK_CONFIG,
    "gemini": GEMINI_CONFIG
}

def get_model_config(model_type, custom_config=None):
    """
    Get configuration for the specified model type.
    
    Args:
        model_type (str): Type of model ("openai", "deepseek", "gemini")
        custom_config (dict, optional): Custom configuration to merge with defaults
        
    Returns:
        dict: Configuration for the model
    """
    model_type = model_type.lower()
    
    if model_type not in DEFAULT_CONFIGS:
        raise ValueError(f"Unsupported model type: {model_type}")
    
    if custom_config is None:
        return DEFAULT_CONFIGS[model_type].copy()
    
    # Merge with defaults
    config = DEFAULT_CONFIGS[model_type].copy()
    config.update(custom_config)
    return config 