"""
Gemini Extractors Package

This package contains Gemini-based document processors:
- gemini_email_processor: Unified processor for email with attachments (images + PDFs)
- text_processor: For text document chunking
"""

from backend.services.processing.rag.extractors.gemini.gemini_email_processor import GeminiEmailProcessor

# Import text processor
try:
    from backend.services.processing.rag.extractors.gemini.text_processor import (
        GeminiTextProcessor,
        process_text_document_from_url
    )
except ImportError:
    # Fallback if text processor is not available
    GeminiTextProcessor = None
    process_text_document_from_url = None

__all__ = [
    "GeminiEmailProcessor"
]

# Only add text processor to exports if it's available
if GeminiTextProcessor is not None:
    __all__.extend([
        "GeminiTextProcessor", 
        "process_text_document_from_url"
    ]) 