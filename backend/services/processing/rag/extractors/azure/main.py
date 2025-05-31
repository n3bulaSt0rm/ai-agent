import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, ParagraphRole

# Get the project root directory for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(os.path.dirname(current_dir))  # src directory
project_root = os.path.dirname(src_dir)  # project root
sys.path.append(project_root)  # Add project root to Python path

# Import from the central config
from backend.core.config import settings

# Setup logging
logger = logging.getLogger(__name__)

# Get Azure Document API credentials from settings
AZURE_DOCUMENT_ENDPOINT = settings.AZURE_DOCUMENT_ENDPOINT
AZURE_DOCUMENT_KEY = settings.AZURE_DOCUMENT_KEY
AZURE_MODEL_ID = "prebuilt-layout"  # Model for extracting text and tables

# Check for required environment variables
if not AZURE_DOCUMENT_ENDPOINT or not AZURE_DOCUMENT_KEY:
    logger.error("Azure Document Intelligence API credentials not set")
    raise ValueError("Azure Document Intelligence API credentials not set. Set AZURE_DOCUMENT_ENDPOINT and AZURE_DOCUMENT_KEY in .env file")

# Output directory configuration
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)


def remove_footnotes_from_content(result):
    """
    Remove footnotes from the document content
    
    Args:
        result: The result object from Azure Document Intelligence
        
    Returns:
        str: Content with footnotes removed
    """
    if not hasattr(result, 'content') or not hasattr(result, 'paragraphs'):
        return result.content if hasattr(result, 'content') else ""
    
    # Original content
    content = result.content
    
    # Find all footnote paragraphs
    footnotes = []
    for paragraph in result.paragraphs:
        if hasattr(paragraph, 'role') and paragraph.role == ParagraphRole.FOOTNOTE and hasattr(paragraph, 'spans'):
            for span in paragraph.spans:
                # Add the span to our list of footnotes to remove
                footnotes.append((span.offset, span.offset + span.length))
    
    # Sort footnotes by offset (descending) to remove from end to start
    # This prevents changing offsets when removing text
    footnotes.sort(reverse=True)
    
    # Remove footnotes from the content
    modified_content = content
    for start, end in footnotes:
        if start < len(modified_content) and end <= len(modified_content):
            modified_content = modified_content[:start] + modified_content[end:]
    
    return modified_content


def process_document(pdf_url, page_range=None):
    """
    Process a document using Azure Document Intelligence SDK directly
    
    Args:
        pdf_url (str): URL to the document
        page_range (str, optional): Range of pages to process (e.g., "1-3")
        
    Returns:
        str: Markdown content of the document with footnotes removed
    """
    try:
        # Validate inputs
        if not pdf_url:
            raise ValueError("Document URL cannot be empty")
            
        if not AZURE_DOCUMENT_ENDPOINT or not AZURE_DOCUMENT_KEY:
            raise ValueError("Azure Document Intelligence configuration missing")
            
        print(f"Processing document: {pdf_url}")
        
        # Initialize the Document Intelligence client
        credential = AzureKeyCredential(AZURE_DOCUMENT_KEY)
        document_intelligence_client = DocumentIntelligenceClient(
            endpoint=AZURE_DOCUMENT_ENDPOINT, 
            credential=credential
        )
        
        # Create the request object
        request = AnalyzeDocumentRequest(url_source=pdf_url)
        
        print(f"Analyzing document with markdown format...")
        # Analyze the document using prebuilt-layout model with markdown format
        poller = document_intelligence_client.begin_analyze_document(
            model_id=AZURE_MODEL_ID,
            body=request,
            pages=page_range,
            output_content_format="markdown",
            features=["languages", "keyValuePairs"]
        )
        
        # Wait for the operation to complete
        result = poller.result()
        
        # Remove footnotes from content
        content_without_footnotes = remove_footnotes_from_content(result)
        
        # Log page range info if provided (for debugging)
        page_info = f"pages_{page_range.replace('-', 'to')}" if page_range else "all_pages"
        print(f"Processed document {page_info} successfully")
        
        # Return content directly instead of file path
        return content_without_footnotes
    
    except HttpResponseError as error:
        print(f"Error from Azure Document Intelligence: {error.message}")
        return None
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        return None


if __name__ == "__main__":
    # Example URL
    pdf_url = "https://aiagenthust.s3.ap-southeast-2.amazonaws.com/files/Bachelor-Computer-Engineering-program.pdf"
    
    # Process document and remove footnotes
    output_path = process_document(pdf_url, page_range="27")
    if output_path:
        print(f"Processing completed successfully")
