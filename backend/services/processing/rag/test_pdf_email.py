"""
Test script for PDF and image attachment processing in Gmail background worker
"""

import logging
import sys
import os
import json
from datetime import datetime
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parents[4]
sys.path.append(str(project_root))

from backend.services.processing.rag.gmail_background_worker import GmailThreadWorker
from backend.services.processing.rag.handler import GmailHandler
from backend.core.config import settings

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def save_response_to_file(content: str, response_type: str):
    """Save response to a timestamped text file"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gemini_response_{response_type}_{timestamp}.txt"
        
        # Create responses directory if it doesn't exist
        responses_dir = Path("gemini_responses")
        responses_dir.mkdir(exist_ok=True)
        
        filepath = responses_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"=== GEMINI RESPONSE - {response_type.upper()} ===\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(content)
            f.write("\n\n" + "=" * 60 + "\n")
            f.write("End of response\n")
        
        logger.info(f"✓ Response saved to: {filepath}")
        return str(filepath)
        
    except Exception as e:
        logger.error(f"Error saving response to file: {e}")
        return None

def test_attachment_extraction():
    """
    Test the improved attachment extraction (both PDF and images)
    """
    logger.info("Testing improved attachment extraction...")
    
    try:
        # Create Gmail handler to get authentication
        handler = GmailHandler()
        handler.authenticate()
        
        # Create worker instance
        worker = GmailThreadWorker(handler.service, handler.user_id)
        
        # Test message ID with attachments (replace with actual message ID)
        test_message_id = "1975613fa6c87f0d"  # Replace with your test message ID
        test_thread_id = "19755b52db9ac903"   # Replace with your test thread ID
        
        logger.info(f"Testing with thread ID: {test_thread_id}")
        
        # Test getting new messages with attachments
        messages = worker._get_new_messages(test_thread_id)
        
        logger.info(f"Retrieved {len(messages)} messages")
        
        for i, msg in enumerate(messages, 1):
            logger.info(f"\n=== MESSAGE {i} ===")
            logger.info(f"From: {msg.get('from', 'Unknown')}")
            logger.info(f"Subject: {msg.get('subject', 'No Subject')}")
            logger.info(f"Text length: {len(msg.get('text_content', ''))}")
            
            # Check image attachments
            image_attachments = msg.get('image_attachments', [])
            logger.info(f"Image attachments: {len(image_attachments)}")
            for j, img in enumerate(image_attachments, 1):
                logger.info(f"  Image {j}: {img.get('filename', 'unknown')} ({img.get('size', 0)} bytes)")
            
            # Check PDF attachments
            pdf_attachments = msg.get('pdf_attachments', [])
            logger.info(f"PDF attachments: {len(pdf_attachments)}")
            for j, pdf in enumerate(pdf_attachments, 1):
                logger.info(f"  PDF {j}: {pdf.get('filename', 'unknown')} ({pdf.get('size', 0)} bytes)")
        
        if messages:
            logger.info("\n=== TESTING GEMINI PROCESSING ===")
            
            # Initialize components
            if worker._initialize_components():
                logger.info("Components initialized successfully")
                
                # Test processing with Gemini
                existing_summary = ""
                new_summary, chunks = worker._process_with_gemini(existing_summary, messages)
                
                logger.info(f"Generated summary length: {len(new_summary)}")
                logger.info(f"Generated chunks: {len(chunks)}")
                
                # Save summary to file
                summary_content = f"=== EXISTING SUMMARY ===\n{existing_summary}\n\n=== NEW SUMMARY ===\n{new_summary}\n\n=== CHUNKS ===\n"
                for idx, chunk in enumerate(chunks, 1):
                    summary_content += f"\nChunk {idx}:\n{chunk}\n{'-'*40}\n"
                
                save_response_to_file(summary_content, "summary_and_chunks")
                
                logger.info("\n=== SUMMARY ===")
                logger.info(new_summary[:500] + "..." if len(new_summary) > 500 else new_summary)
                
                logger.info("\n=== CHUNKS ===")
                for idx, chunk in enumerate(chunks, 1):
                    logger.info(f"Chunk {idx}: {chunk[:100]}..." if len(chunk) > 100 else f"Chunk {idx}: {chunk}")
                    
                # Save individual chunks to file
                chunks_content = "\n".join([f"=== CHUNK {i+1} ===\n{chunk}\n" for i, chunk in enumerate(chunks)])
                save_response_to_file(chunks_content, "individual_chunks")
                
            else:
                logger.error("Failed to initialize components")
        else:
            logger.info("No messages found for testing")
        
    except Exception as e:
        error_msg = f"Error in test: {e}"
        logger.error(error_msg, exc_info=True)
        save_response_to_file(error_msg, "error")

def test_specific_attachments():
    """
    Test with specific message containing both PDF and image attachments
    """
    logger.info("Testing specific message with attachments...")
    
    try:
        from backend.services.processing.rag.utils import extract_all_attachments
        
        # Create Gmail handler
        handler = GmailHandler()
        handler.authenticate()
        
        # Test with specific message ID (replace with your test message)
        test_message_id = "1975613fa6c87f0d"  # Replace with actual message ID
        
        # Get message details
        msg = handler.service.users().messages().get(
            userId=handler.user_id,
            id=test_message_id,
            format='full'
        ).execute()
        
        logger.info(f"Testing message: {test_message_id}")
        
        # Extract all attachments
        attachments = extract_all_attachments(
            handler.service, 
            handler.user_id, 
            msg['payload'], 
            test_message_id
        )
        
        logger.info(f"Found {len(attachments)} total attachments")
        
        # Save attachment info to file
        attachment_info = f"Message ID: {test_message_id}\nTotal attachments: {len(attachments)}\n\n"
        for i, attachment in enumerate(attachments, 1):
            attachment_info += f"Attachment {i}:\n"
            attachment_info += f"  Type: {attachment.get('attachment_type', 'unknown')}\n"
            attachment_info += f"  Filename: {attachment.get('filename', 'unknown')}\n"
            attachment_info += f"  MIME type: {attachment.get('mime_type', 'unknown')}\n"
            attachment_info += f"  Size: {attachment.get('size', 0)} bytes\n\n"
        
        save_response_to_file(attachment_info, "attachment_extraction")
        
        for i, attachment in enumerate(attachments, 1):
            logger.info(f"Attachment {i}:")
            logger.info(f"  Type: {attachment.get('attachment_type', 'unknown')}")
            logger.info(f"  Filename: {attachment.get('filename', 'unknown')}")
            logger.info(f"  MIME type: {attachment.get('mime_type', 'unknown')}")
            logger.info(f"  Size: {attachment.get('size', 0)} bytes")
        
    except Exception as e:
        error_msg = f"Error testing specific attachments: {e}"
        logger.error(error_msg, exc_info=True)
        save_response_to_file(error_msg, "error")

if __name__ == "__main__":
    print("Gmail PDF and Image Processing Test")
    print("=" * 50)
    
    # Test 1: Basic attachment extraction
    test_specific_attachments()
    
    print("\n" + "=" * 50)
    
    # Test 2: Full workflow with Gemini processing
    test_attachment_extraction()
    
    print("\nTest completed!")
    print("Check the 'gemini_responses' directory for detailed outputs.") 