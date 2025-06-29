"""
Gmail Indexing Worker using Cron Expression
"""

import logging
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import threading
import json
from email.utils import parsedate_to_datetime

from backend.common.config import settings
from backend.adapter.sql.metadata import get_metadata_db
from backend.services.processing.rag.extractors.gemini.gemini_email_processor import GeminiEmailProcessor
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.services.processing.rag.common.qdrant import ChunkData
from backend.services.processing.rag.common.utils import (
    extract_text_content, extract_all_attachments, 
    run_cron_scheduler
)

logger = logging.getLogger(__name__)

class GmailIndexingWorker:
    """Gmail indexing worker using cron expression for scheduling"""
    
    def __init__(self, 
                 gmail_service,  
                 user_id: str,
                 gemini_processor: Optional[GeminiEmailProcessor] = None,
                 embedding_module: Optional[VietnameseEmbeddingModule] = None):  
        self.gmail_service = gmail_service
        self.user_id = user_id
        
        self.cron_expression = settings.WORKER_CRON_EXPRESSION
        self.collection_name = settings.EMAIL_QA_COLLECTION
        
        self.metadata_db = get_metadata_db()
        
        self.gemini_email_processor = gemini_processor
        self.embedding_module = embedding_module
        
        self.is_running = False
        self.is_scheduled = False
        self.worker_thread = None
        
        logger.info("Gmail Indexing Worker initialized - Cron: " + self.cron_expression + ", Collection: " + self.collection_name)
    
    def _initialize_components(self):
        try:
            if not self.gemini_email_processor:
                self.gemini_email_processor = GeminiEmailProcessor()
                logger.info("✓ Gemini Email Processor initialized")
            else:
                logger.info("✓ Using shared Gemini Email Processor")
            
            if not self.embedding_module:
                from backend.services.processing.rag.common.utils import initialize_embedding_module
                self.embedding_module = initialize_embedding_module(self.collection_name)
                if not self.embedding_module:
                    return False
                logger.info("✓ Embedding Module initialized")
            else:
                logger.info("✓ Using shared Embedding Module")
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
            return False
    
    def _get_new_messages(self, thread_id: str, last_processed_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get new messages from thread since last processed"""
        try:
            thread_messages = self.gmail_service.users().threads().get(
                userId=self.user_id,
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread_messages.get('messages', [])
            if not messages:
                return []
            
            # Find starting point
            start_processing = last_processed_id is None
            new_messages = []
            
            for message in messages:
                message_id = message['id']
                
                if not start_processing and message_id == last_processed_id:
                    start_processing = True
                    continue
                
                if start_processing:
                    headers = {h['name']: h['value'] for h in message['payload']['headers']}
                    text_content = extract_text_content(message['payload'])
                    
                    # Extract both images and PDFs
                    all_attachments = extract_all_attachments(
                        self.gmail_service, self.user_id, message['payload'], message_id
                    )
                    
                    # Separate attachments by type for easier processing
                    image_attachments = [att for att in all_attachments if att.get('attachment_type') == 'image']
                    pdf_attachments = [att for att in all_attachments if att.get('attachment_type') == 'pdf']
                    
                    new_messages.append({
                        'id': message_id,
                        'from': headers.get('From', ''),
                        'subject': headers.get('Subject', ''),
                        'date': headers.get('Date', ''),
                        'text_content': text_content,
                        'image_attachments': image_attachments,
                        'pdf_attachments': pdf_attachments
                    })
            
            return new_messages
            
        except Exception as e:
            logger.error(f"Error getting messages for thread {thread_id}: {e}")
            return []
    
    def _process_with_gemini(self, existing_summary: str, new_messages: List[Dict[str, Any]]) -> tuple[str, List[str]]:
        """Process messages with Gemini to create summary and chunks"""
        try:
            if not new_messages:
                return existing_summary, []
            
            # Process each message with the unified processor
            all_processed_content = []
            
            for i, msg in enumerate(new_messages, 1):
                logger.info(f"Processing message {i}/{len(new_messages)}")
                
                # Get attachments
                image_attachments = msg.get('image_attachments', [])
                pdf_attachments = msg.get('pdf_attachments', [])
                
                # Process message with attachments
                processed_content = self.gemini_email_processor.process_email_with_attachments(
                    email_text=f"Email {i}:\nTừ: {msg['from']}\nTiêu đề: {msg['subject']}\n\nNội dung:\n{msg['text_content']}",
                    image_attachments=image_attachments,
                    pdf_attachments=pdf_attachments
                )
                
                all_processed_content.append(processed_content)
            
            # Combine all processed content
            combined_content = "\n\n" + "="*50 + "\n\n".join(all_processed_content)
            
            # Generate summary and chunks
            new_summary, chunks_list = self.gemini_email_processor.generate_summary_and_chunks(
                existing_summary=existing_summary,
                processed_content=combined_content
            )
            
            return new_summary, chunks_list
            
        except Exception as e:
            logger.error(f"Error processing with Gemini: {e}")
            return existing_summary or "Lỗi xử lý Gemini", []
    
    def _embed_chunks(self, chunks: List[str], embedding_id: str, file_created_at: str, thread_id: str = None) -> bool:
        """Embed chunks to Qdrant"""
        try:
            if not chunks:
                return True
            
            source = f"gmail_thread"
            
            chunk_data_list = []
            for i, content in enumerate(chunks):
                chunk_data_list.append(ChunkData(
                    chunk_id=i + 1,
                    content=content,
                    file_id=embedding_id,
                    file_created_at=file_created_at or datetime.now().isoformat(),
                    parent_chunk_id=0,
                    source=source
                ))
            
            self.embedding_module.index_documents(chunk_data_list)
            logger.info(f"✓ Embedded {len(chunks)} chunks")
            return True
            
        except Exception as e:
            logger.error(f"Error embedding chunks: {e}")
            return False
    
    def _get_threads_to_process(self) -> List[Dict[str, Any]]:
        """Get threads that need processing - only non-outdated threads"""
        try:
            return self.metadata_db.get_threads_to_process()
        except Exception as e:
            logger.error(f"Error getting threads to process: {e}")
            return []
    
    def _process_single_thread(self, thread_record: Dict[str, Any]) -> bool:
        thread_id = thread_record['thread_id']
        existing_summary = thread_record.get('context_summary', '')
        last_processed_id = thread_record.get('last_processed_message_id')
        old_embedding_id = thread_record.get('embedding_id')  
        
        try:
            new_messages = self._get_new_messages(thread_id, last_processed_id)
            if not new_messages:
                return True
            
            new_summary, chunks = self._process_with_gemini(existing_summary, new_messages)
            
            new_last_processed_id = new_messages[-1]['id']
            new_embedding_id = thread_id + "," + new_last_processed_id
            
            try:
                latest_email_date = new_messages[-1]['date']
                if latest_email_date:
                    try:
                        parsed_date = parsedate_to_datetime(latest_email_date)
                        if parsed_date:
                            latest_email_date = parsed_date.isoformat()
                        else:
                            logger.warning(f"Failed to parse email date: {latest_email_date}")
                            latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
                    except Exception as date_error:
                        logger.error(f"Error parsing email date '{latest_email_date}': {date_error}")
                        latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
                else:
                    latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
            except Exception as e:
                logger.error(f"Error getting email date for thread {thread_id}: {e}")
                latest_email_date = thread_record.get('updated_at') or datetime.now().isoformat()
            
            # Embed new chunks first
            if not self._embed_chunks(chunks, new_embedding_id, latest_email_date, thread_id):
                logger.error(f"Failed to embed new chunks for thread {thread_id}")
                return False
            
            # Update metadata in database
            success = self.metadata_db.upsert_gmail_thread(
                thread_id=thread_id,
                context_summary=new_summary,
                last_processed_message_id=new_last_processed_id,
                embedding_id=new_embedding_id
            )
            
            if not success:
                logger.error(f"Failed to update metadata for thread {thread_id}")
                # Rollback: delete the newly embedded chunks
                try:
                    qdrant_manager = self.embedding_module.qdrant_manager
                    qdrant_manager.delete_chunks_by_file_id(new_embedding_id)
                    logger.info(f"Rolled back newly embedded chunks for thread {thread_id}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback chunks for thread {thread_id}: {rollback_error}")
                return False
            
            # Only delete old chunks after successful metadata update
            if old_embedding_id and old_embedding_id != new_embedding_id:
                try:
                    logger.info(f"Deleting old chunks for previous embedding_id: {old_embedding_id}")
                    qdrant_manager = self.embedding_module.qdrant_manager
                    delete_success = qdrant_manager.delete_chunks_by_file_id(old_embedding_id)
                    if delete_success:
                        logger.info(f"✓ Successfully deleted old chunks for previous embedding_id: {old_embedding_id}")
                    else:
                        logger.warning(f"Failed to delete old chunks for previous embedding_id: {old_embedding_id}")
                except Exception as delete_error:
                    logger.error(f"Error deleting old chunks for embedding_id {old_embedding_id}: {delete_error}")
                    # Don't return False here as the main operation succeeded
            
            if success:
                logger.info("✓ Processed thread " + thread_id + ", embedded " + str(len(chunks)) + " chunks with embedding_id: " + new_embedding_id)
            return success
            
        except Exception as e:
            logger.error("Error processing thread " + thread_id + ": " + str(e))
            return False
    
    def _run_processing(self):
        """Run the main processing loop"""
        if self.is_running:
            logger.warning("Processing already running")
            return
        
        self.is_running = True
        logger.info("Starting Gmail Thread Processing")
        
        try:
            if not self._initialize_components():
                logger.error("Failed to initialize components")
                return
            
            threads = self._get_threads_to_process()
            if not threads:
                logger.info("No threads to process")
                return
            
            logger.info("Processing " + str(len(threads)) + " threads")
            
            processed = 0
            for thread_record in threads:
                if not self.is_running:
                    break
                
                thread_id = thread_record.get('thread_id', 'unknown')
                logger.info(f"Processing thread {processed + 1}/{len(threads)}: {thread_id}")
                
                if self._process_single_thread(thread_record):
                    processed += 1
                    logger.info(f" Successfully processed thread {thread_id}")
                else:
                    logger.error(f" Failed to process thread {thread_id}")
                
                time.sleep(5) 
            
            logger.info("Processing Complete: " + str(processed) + "/" + str(len(threads)))
            
        except Exception as e:
            logger.error("Error in processing: " + str(e))
        finally:
            self.is_running = False
    
    def _scheduler_loop(self):
        """Run the cron scheduler loop"""
        run_cron_scheduler(
            self.cron_expression,
            self._run_processing,
            "Gmail Indexing Worker",
            None
        )
    
    def start(self):
        """Start the indexing worker"""
        if self.worker_thread and self.worker_thread.is_alive():
            logger.warning("Worker already running")
            return
        
        self.is_scheduled = True
        self.worker_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Gmail indexing worker started")
    
    def stop(self):
        """Stop the worker"""
        self.is_running = False
        self.is_scheduled = False
        logger.info("Gmail indexing worker stopped")
    
    def run_once(self):
        """Run processing once"""
        logger.info("Running Gmail indexing once...")
        self._run_processing()

 