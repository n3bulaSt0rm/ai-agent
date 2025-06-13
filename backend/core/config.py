from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Dict, Any, List
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
    API_BASE_URL: str = Field(default="http://localhost:8000")
    
    # Processing service settings
    PROCESSING_PORT: int = Field(default=8081, description="Port for the processing service")
    PROCESSING_HOST: str = Field(default="0.0.0.0", description="Host for the processing service")
    
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
    
    # Redis settings for dramatiq task queue
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)
    REDIS_PASSWORD: str = Field(default="", description="Redis password (optional)")
    
    # Topic/exchange names
    PDF_PROCESSING_TOPIC: str = Field(default="pdf-processing-topic")
    
    # Qdrant settings
    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_COLLECTION_NAME: str = Field(default="vietnamese_chunks_test")
    
    # Processing settings
    EMBEDDING_MODEL: str = Field(default="AITeamVN/Vietnamese_Embedding_v2")
    CHUNK_SIZE: int = Field(default=1000)
    CHUNK_OVERLAP: int = Field(default=200)
    PROCESSING_THREADS: int = Field(default=2)
    
    # Chunker configuration
    CHUNKER_TYPE: str = Field(default="recursive", description="Type of chunker to use: 'semantic' or 'recursive'")
    SEMANTIC_CHUNKER_THRESHOLD: float = Field(default=0.3)
    DENSE_MODEL_NAME: str = Field(default="AITeamVN/Vietnamese_Embedding_v2", description="Dense embedding model name")
    SPARSE_MODEL_NAME: str = Field(default="Qdrant/bm25", description="Sparse embedding model name")
    RERANKER_MODEL_NAME: str = Field(default="AITeamVN/Vietnamese_Reranker", description="Reranker model name")
    VECTOR_SIZE: int = Field(default=1024, description="Size of vector embeddings")
    RECURSIVE_CHUNKER_SIZE: int = Field(default=1800)
    RECURSIVE_CHUNKER_OVERLAP: int = Field(default=220)
    RECURSIVE_CHUNKER_MIN_LENGTH: int = Field(default=50)       
    RECURSIVE_CHUNKER_MAX_SEQ_LENGTH: int = Field(default=2048)
    QDRANT_BATCH_SIZE: int = Field(default=8)
    
    # Gmail settings
    GMAIL_TOKEN_PATH: str = Field(default="D:/Project/DATN_HUST/ai-agent/secret/dev/token.json")
    GMAIL_POLL_INTERVAL: int = Field(default=30, description="Gmail API polling interval in seconds")
    GMAIL_EMAIL_ADDRESS: str = Field(default="", description="Gmail email address for identifying sent emails")
    GOOGLE_API_KEY: str = Field(default="")
    
    # DeepSeek API settings
    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_API_URL: str = Field(default="https://api.deepseek.com/v1/chat/completions", description="DeepSeek API endpoint")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat")
    
    # Email monitoring settings
    DRAFT_CHECK_INTERVAL: int = Field(default=240, description="Draft checking interval in seconds (4 minutes)")
    EMAIL_CHECK_INTERVAL: int = Field(default=600, description="Email checking interval in seconds (10 minutes)")
    MONITORING_SLEEP_INTERVAL: int = Field(default=60, description="Monitoring loop sleep interval in seconds (1 minute)")
    
    # Background Worker settings for Gmail Thread Processing
    WORKER_CRON_EXPRESSION: str = Field(default="0 4 * * *", description="Cron expression for worker schedule (default: 4 AM every day)")
    EMAIL_QA_COLLECTION: str = Field(default="email_qa", description="Qdrant collection name for email embeddings")
    CLEANUP_CRON_EXPRESSION: str = Field(default="0 2 1 * *", description="Cron expression for cleanup schedule (default: 2 AM on 1st day of every month)")
    OUTDATED_CLEANUP_CRON_EXPRESSION: str = Field(default="0 1 1 */3 *", description="Cron expression for outdated threads cleanup (default: 1 AM on 1st day every 3 months)")
    
    # Logging settings
    LOG_LEVEL: str = Field(default="INFO")
    
    # Google OAuth settings
    GOOGLE_CLIENT_ID: str = Field(default="", description="Google OAuth Client ID")
    GOOGLE_CLIENT_SECRET: str = Field(default="", description="Google OAuth Client Secret")
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend URL for OAuth redirects")
    
    # Azure Document Intelligence API settings
    AZURE_DOCUMENT_ENDPOINT: str = Field(default="", description="Azure Document Intelligence endpoint")
    AZURE_DOCUMENT_KEY: str = Field(default="", description="Azure Document Intelligence API key")
    
    # Storage Limits in MB
    STORAGE_LIMIT_MB: int = Field(default=1000)
    
    class Config:
        env_file = os.path.join(BASE_DIR, ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True

# Create global settings instance
settings = Settings()

def get_settings() -> Settings:
    """Get the settings instance."""
    return settings