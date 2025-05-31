from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os
from pathlib import Path

# Get the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    """Centralized application configuration using Pydantic BaseSettings"""
    
    # Base settings
    APP_NAME: str = Field(default="AI-Agent PDF Management")
    DEBUG: bool = Field(default=False)
    
    # Web service settings
    WEB_HOST: str = Field(default="0.0.0.0")
    WEB_PORT: int = Field(default=8000)
    
    # Authentication settings
    ADMIN_USERNAME: str = Field(default="admin")
    ADMIN_PASSWORD: str = Field(default="admin123")
    AUTH_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24) 
    AUTH_SECRET_KEY: str = Field(default="secret_key_change_in_production")
    
    # Database settings
    DATABASE_PATH: str = Field(default="data/admin.db")
    
    # AWS S3 settings
    AWS_ACCESS_KEY_ID: str = Field(default="")
    AWS_SECRET_ACCESS_KEY: str = Field(default="")
    AWS_REGION: str = Field(default="ap-southeast-2")
    S3_BUCKET_NAME: str = Field(default="aiagenthust")
    
    # Messaging settings - RabbitMQ
    RABBITMQ_HOST: str = Field(default="cougar.rmq.cloudamqp.com")
    RABBITMQ_PORT: int = Field(default=5671)  # 5671 cho TLS
    RABBITMQ_USERNAME: str = Field(default="afupjdbk")
    RABBITMQ_PASSWORD: str = Field(default="Q07Fb5SHeW_U9GbpNA0ojPL5osTGoWse")
    RABBITMQ_VHOST: str = Field(default="afupjdbk")
    
    # Topic/exchange names
    PDF_PROCESSING_TOPIC: str = Field(default="pdf-processing-topic")
    
    # Qdrant settings
    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_COLLECTION_NAME: str = Field(default="vietnamese_chunks_test")
    
    # Processing settings
    EMBEDDING_MODEL: str = Field(default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    CHUNK_SIZE: int = Field(default=1000)
    CHUNK_OVERLAP: int = Field(default=200)
    PROCESSING_THREADS: int = Field(default=2)

    # Webhook settings
    WEB_SERVICE_URL: str = Field(default="http://localhost:8000/api/webhook/status-update")
    
    # Gmail API settings
    GMAIL_CREDENTIALS_PATH: str = Field(default="secret/credentials.json")
    GMAIL_TOKEN_PATH: str = Field(default="token.json")
    GMAIL_POLL_INTERVAL: int = Field(default=60)  # Seconds
    
    # DeepSeek API settings
    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_API_URL: str = Field(default="https://api.deepseek.com/v1/chat/completions", description="DeepSeek API endpoint")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat")
    
    # Logging settings
    LOG_LEVEL: str = Field(default="INFO")
    
    # Azure Document Intelligence API settings
    AZURE_DOCUMENT_ENDPOINT: str = Field(default="", description="Azure Document Intelligence endpoint")
    AZURE_DOCUMENT_KEY: str = Field(default="", description="Azure Document Intelligence API key")

    class Config:
        env_file = os.path.join(BASE_DIR, ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True

# Create global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Get the settings instance."""
    return settings