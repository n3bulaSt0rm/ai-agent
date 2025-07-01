#!/usr/bin/env python3
"""
Real Gmail Indexing Worker Test Script
Tests with actual Gmail API and Gemini API calls
"""

import sys
import os
import logging
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.processing.rag.gmail_indexing_worker import GmailIndexingWorker
from backend.services.processing.rag.handler import GmailHandler
from backend.common.config import settings
from backend.adapter.sql.metadata import MetadataDB
from backend.services.processing.rag.common.utils import initialize_embedding_module

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_real_services():
    """Initialize real services for testing"""
    
    print("🔧 Setting up real services...")
    
    # 1. Gmail Service
    try:
        gmail_handler = GmailHandler()
        gmail_handler.authenticate()  # This creates the Gmail service
        print("✅ Gmail service initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Gmail service: {e}")
        print("💡 Make sure you have Gmail API credentials configured")
        return None, None, None
    
    # 2. Metadata DB
    try:
        metadata_db = MetadataDB()
        print("✅ Metadata DB initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Metadata DB: {e}")
        return None, None, None
    
    # 3. Embedding Module
    try:
        embedding_module = initialize_embedding_module(settings.EMAIL_QA_COLLECTION)
        if embedding_module:
            print("✅ Embedding module initialized")
        else:
            print("❌ Failed to initialize embedding module")
            return None, None, None
    except Exception as e:
        print(f"❌ Failed to initialize embedding module: {e}")
        return None, None, None
    
    return gmail_handler, metadata_db, embedding_module

def get_test_thread_id():
    """Get a thread ID to test with"""
    
    print("\n📧 Getting a test thread ID...")
    
    try:
        gmail_handler = GmailHandler()
        gmail_handler.authenticate()
        
        # Get list of threads (limit to recent ones)
        results = gmail_handler.service.users().threads().list(
            userId='me',
            maxResults=10,
            q='subject:học bổng OR subject:sinh viên OR subject:CTSV'  # Search for relevant threads
        ).execute()
        
        threads = results.get('threads', [])
        
        if not threads:
            print("❌ No threads found with the search criteria")
            print("💡 Try manually entering a thread ID")
            return None
        
        print(f"📋 Found {len(threads)} relevant threads:")
        
        # Get thread details for selection
        for i, thread in enumerate(threads[:5], 1):  # Show max 5
            try:
                thread_detail = gmail_handler.service.users().threads().get(
                    userId='me',
                    id=thread['id'],
                    format='metadata'
                ).execute()
                
                messages = thread_detail.get('messages', [])
                if messages:
                    # Get subject from first message
                    headers = messages[0].get('payload', {}).get('headers', [])
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    message_count = len(messages)
                    
                    print(f"  {i}. Thread ID: {thread['id']}")
                    print(f"     Subject: {subject[:80]}...")
                    print(f"     Messages: {message_count}")
                    print()
                    
            except Exception as e:
                logger.warning(f"Error getting thread details for {thread['id']}: {e}")
        
        # Return first thread for automatic testing
        if threads:
            selected_thread = threads[0]['id']
            print(f"🎯 Auto-selected thread: {selected_thread}")
            return selected_thread
            
    except Exception as e:
        print(f"❌ Error getting threads: {e}")
        return None

def test_worker_components(worker, thread_id):
    """Test individual worker components"""
    
    print(f"\n🧪 Testing worker components with thread: {thread_id}")
    print("=" * 60)
    
    try:
        # Test 1: Fetch thread messages
        print("\n🔍 Test 1: Fetching thread messages...")
        raw_messages = worker._fetch_thread_messages(thread_id)
        print(f"✅ Fetched {len(raw_messages)} raw messages")
        
        if not raw_messages:
            print("❌ No messages found in thread")
            return False
        
        # Test 2: Process messages
        print("\n🔄 Test 2: Processing messages...")
        processed_messages = worker._process_messages_list(raw_messages)
        print(f"✅ Processed {len(processed_messages)} messages")
        
        # Display message summary
        for i, msg in enumerate(processed_messages, 1):
            print(f"  📧 Email {i}: From {msg['from']}")
            print(f"     Subject: {msg['subject'][:60]}...")
            print(f"     Date: {msg['date']}")
            
            # Check for attachments
            image_count = len(msg.get('image_attachments', []))
            pdf_count = len(msg.get('pdf_attachments', []))
            if image_count > 0 or pdf_count > 0:
                print(f"     📎 Attachments: {image_count} images, {pdf_count} PDFs")
            print()
        
        # Test 3: Get all messages
        print("\n📥 Test 3: Getting all messages...")
        all_messages = worker._get_all_messages(thread_id)
        print(f"✅ Retrieved {len(all_messages)} total messages")
        
        # Test 4: Get new messages (simulate last processed as first message)
        if len(processed_messages) > 1:
            print("\n📬 Test 4: Getting new messages...")
            first_msg_id = processed_messages[0]['id']
            new_messages = worker._get_new_messages(thread_id, first_msg_id)
            print(f"✅ Retrieved {len(new_messages)} new messages (after first message)")
        
        # Test 5: Create prompts
        print("\n📝 Test 5: Creating prompts...")
        
        # Build thread content
        thread_content = ""
        for i, msg in enumerate(all_messages, 1):
            email_text = f"""
=== EMAIL {i} ===
Từ: {msg['from']}
Đến: {msg.get('to', '')}
Tiêu đề: {msg['subject']}
Ngày: {msg['date']}
Nội dung: {msg['text_content'][:500]}...
"""
            thread_content += email_text + "\n"
        
        # Test chunking prompt
        chunks_prompt = worker._create_chunks_extraction_prompt(thread_content)
        print(f"✅ Chunking prompt created ({len(chunks_prompt)} chars)")
        
        # Test summary prompt
        existing_summary = "Test existing summary ||| Test knowledge summary"
        summary_prompt = worker._create_summary_update_prompt(thread_content, existing_summary)
        print(f"✅ Summary prompt created ({len(summary_prompt)} chars)")
        
        return True
        
    except Exception as e:
        print(f"❌ Component test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_full_workflow(worker, thread_id):
    """Test the complete workflow"""
    
    print(f"\n🚀 Testing complete workflow with thread: {thread_id}")
    print("=" * 60)
    
    try:
        # Simulate processing a thread with new messages
        print("\n📊 Simulating thread processing...")
        
        # Get thread record (simulate from DB)
        thread_record = {
            'thread_id': thread_id,
            'context_summary': 'Existing summary for testing',
            'last_processed_message_id': None,  # Process all messages
            'embedding_id': None
        }
        
        print(f"📋 Thread record: {thread_record}")
        
        # Test the main processing function
        print("\n🔄 Testing _process_single_thread...")
        
        # Get new messages first
        new_messages = worker._get_new_messages(
            thread_record['thread_id'], 
            thread_record.get('last_processed_message_id')
        )
        
        if not new_messages:
            print("❌ No new messages to process")
            return False
        
        print(f"✅ Found {len(new_messages)} messages to process")
        
        # Test Gemini conversation creation
        print("\n🤖 Testing Gemini conversation...")
        conversation = worker._create_gemini_conversation()
        
        if not conversation:
            print("❌ Failed to create Gemini conversation")
            print("💡 Check your GOOGLE_API_KEY in settings")
            return False
        
        print("✅ Gemini conversation created successfully")
        
        # Test the 2-step process with real Gemini calls
        print("\n⚡ Testing 2-step Gemini process...")
        
        try:
            updated_summary, chunks = worker._process_with_gemini(
                thread_record.get('context_summary', ''),
                new_messages,
                thread_id
            )
            
            print(f"✅ 2-step process completed successfully!")
            print(f"📄 Updated summary length: {len(updated_summary)} characters")
            print(f"🧩 Generated chunks: {len(chunks)}")
            
            # Display chunks
            if chunks:
                print("\n📋 Generated chunks:")
                for i, chunk in enumerate(chunks, 1):
                    print(f"  🧩 Chunk {i}: {chunk[:100]}...")
                    if len(chunk) > 100:
                        print(f"      ... (total {len(chunk)} characters)")
                    print()
            
            # Display summary
            if updated_summary:
                print(f"\n📄 Updated summary:")
                if '|||' in updated_summary:
                    parts = updated_summary.split('|||')
                    print(f"  📝 Conversation summary: {parts[0].strip()[:200]}...")
                    print(f"  🧠 Knowledge summary: {parts[1].strip()[:200]}...")
                else:
                    print(f"  📝 Summary: {updated_summary[:400]}...")
            
            return True
            
        except Exception as e:
            print(f"❌ Gemini processing failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print(f"❌ Full workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    
    print("🚀 Gmail Indexing Worker - Real API Test")
    print("=" * 50)
    
    print("\n⚠️  Warning: This test uses real APIs:")
    print("  • Gmail API (reads your actual emails)")
    print("  • Gemini API (consumes API quota)")
    print("  • Qdrant Database (creates/updates vectors)")
    
    # Setup services
    gmail_handler, metadata_db, embedding_module = setup_real_services()
    
    if not all([gmail_handler, metadata_db, embedding_module]):
        print("\n❌ Failed to setup required services")
        return False
    
    # Get test thread
    thread_id = get_test_thread_id()
    if not thread_id:
        print("\n💡 You can manually specify a thread ID:")
        thread_id = input("Enter Gmail thread ID (or press Enter to skip): ").strip()
        
        if not thread_id:
            print("❌ No thread ID provided")
            return False
    
    # Initialize worker
    print(f"\n🔧 Initializing Gmail worker...")
    
    try:
        worker = GmailIndexingWorker(
            gmail_service=gmail_handler.service,
            user_id='me',
            gemini_processor=None,  # Will be initialized automatically
            embedding_module=embedding_module
        )
        worker.metadata_db = metadata_db
        
        print("✅ Gmail worker initialized successfully")
        
    except Exception as e:
        print(f"❌ Failed to initialize worker: {e}")
        return False
    
    # Run tests
    print(f"\n🧪 Starting tests with thread: {thread_id}")
    
    # Test components
    component_success = test_worker_components(worker, thread_id)
    
    if component_success:
        # Test full workflow
        workflow_success = test_full_workflow(worker, thread_id)
        
        if workflow_success:
            print("\n" + "=" * 60)
            print("🎉 ALL TESTS PASSED!")
            print("=" * 60)
            print("✅ Gmail Worker is working correctly with real APIs")
            print("✅ Ready for production use")
            return True
    
    print("\n" + "=" * 60)
    print("❌ SOME TESTS FAILED")
    print("=" * 60)
    print("💡 Check the error messages above for debugging")
    return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🚀 Test completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Test failed!")
        sys.exit(1) 