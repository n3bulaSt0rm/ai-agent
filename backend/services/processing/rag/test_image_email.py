"""
Debug script for testing image attachment extraction
"""

import asyncio
import logging
import sys
import os
import json
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parents[4]
sys.path.append(str(project_root))

from backend.services.processing.rag.handler import GmailHandler
from backend.core.config import settings

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def debug_message_structure(handler, message_id):
    """
    Debug the structure of a specific message to understand how attachments are stored
    """
    logger.info(f"Debugging message structure for: {message_id}")
    
    try:
        # Get the full message
        msg = handler.service.users().messages().get(
            userId=handler.user_id, 
            id=message_id,
            format='full'
        ).execute()
        
        logger.info("=== MESSAGE STRUCTURE DEBUG ===")
        
        # Save to file for inspection
        debug_file = f"debug_message_{message_id}.json"
        with open(debug_file, 'w', encoding='utf-8') as f:
            json.dump(msg, f, indent=2, ensure_ascii=False)
        logger.info(f"Full message structure saved to: {debug_file}")
        
        # Analyze payload structure
        payload = msg.get('payload', {})
        logger.info(f"Main payload mimeType: {payload.get('mimeType', 'Unknown')}")
        
        def analyze_part(part, level=0):
            indent = "  " * level
            mime_type = part.get('mimeType', '')
            filename = part.get('filename', '')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')
            data = body.get('data')
            
            logger.info(f"{indent}Part:")
            logger.info(f"{indent}  - mimeType: {mime_type}")
            logger.info(f"{indent}  - filename: {filename}")
            logger.info(f"{indent}  - attachmentId: {attachment_id}")
            logger.info(f"{indent}  - has inline data: {bool(data)}")
            
            if mime_type.startswith('image/'):
                logger.info(f"{indent}  *** IMAGE FOUND ***")
                logger.info(f"{indent}      Type: {'External' if attachment_id else 'Inline'}")
                logger.info(f"{indent}      Size: {body.get('size', 'Unknown')}")
            
            # Process nested parts
            if 'parts' in part:
                logger.info(f"{indent}  - has {len(part['parts'])} subparts")
                for i, subpart in enumerate(part['parts']):
                    logger.info(f"{indent}    Subpart {i+1}:")
                    analyze_part(subpart, level + 2)
        
        # Analyze structure
        if 'parts' in payload:
            logger.info(f"Message has {len(payload['parts'])} main parts")
            for i, part in enumerate(payload['parts']):
                logger.info(f"Main part {i+1}:")
                analyze_part(part, 1)
        else:
            logger.info("Single part message")
            analyze_part(payload, 0)
            
    except Exception as e:
        logger.error(f"Error debugging message structure: {e}")

async def test_specific_message_debug():
    """
    Test image extraction with detailed debugging
    """
    message_id = "1975613fa6c87f0d"  # Replace with your message ID
        
    logger.info(f"Testing image extraction for message: {message_id}")
    
    try:
        # Create handler with Gemini enabled
        handler = GmailHandler(use_gemini=True)
        handler.authenticate()
        
        # Debug message structure first
        debug_message_structure(handler, message_id)
        
        logger.info("\n=== TESTING IMAGE EXTRACTION ===")
        
        # Get specific message
        msg = handler.service.users().messages().get(
            userId=handler.user_id, 
            id=message_id
        ).execute()
        
        # Process the email body (including images)
        body = handler._get_email_body(msg)
        
        logger.info(f"Processed body length: {len(body)} characters")
        logger.info("=== PROCESSED BODY CONTENT ===")
        logger.info(body)
        
        # Check for different types of image processing results
        if "=== ẢNH ĐÍNH KÈM ===" in body or "📸" in body:
            logger.info("✅ Images found with basic markers!")
        elif "📸 **Phân tích ảnh" in body:
            logger.info("✅ Images were processed by Gemini!")
        elif len(body) > 200 and ("hình ảnh" in body.lower() or "ảnh" in body.lower() or "cuộc trò chuyện" in body.lower()):
            logger.info("✅ Images likely processed by Gemini (detected by content analysis)!")
        else:
            logger.info("❌ No images found in processed content")
            
    except Exception as e:
        logger.error(f"Error testing message: {e}")

if __name__ == "__main__":
    print("=== Gmail Image Extraction Debug ===")
    print(f"Gemini API Key: {'✅ Configured' if settings.GOOGLE_API_KEY else '❌ Not configured'}")
    print(f"Gmail Token Path: {settings.GMAIL_TOKEN_PATH}")
    print()
    
    # Run the debug test
    asyncio.run(test_specific_message_debug()) 