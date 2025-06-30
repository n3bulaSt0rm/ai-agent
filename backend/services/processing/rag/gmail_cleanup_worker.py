"""
Gmail Cleanup Worker for Outdated Threads
"""

import logging
import time
import threading
from datetime import datetime

from backend.common.config import settings
from backend.adapter.sql.metadata import get_metadata_db
from backend.services.processing.rag.embedders.text_embedder import VietnameseEmbeddingModule
from backend.services.processing.rag.common.utils import (
    calculate_cutoff_date_from_cron, run_cron_scheduler
)

logger = logging.getLogger(__name__)

class GmailCleanupWorker:
    
    def __init__(self, embedding_module: VietnameseEmbeddingModule = None):
        self.outdated_cron_expression = settings.OUTDATED_CLEANUP_CRON_EXPRESSION
        self.collection_name = settings.EMAIL_QA_COLLECTION
        self.metadata_db = get_metadata_db()
        
        self.embedding_module = embedding_module
        
        self.is_running = False
        self.is_scheduled = False
        self.worker_thread = None
        
        logger.info(f"Cleanup Worker initialized - Cron: {self.outdated_cron_expression}")
    

    
    def _calculate_cutoff_date(self) -> str:
        return calculate_cutoff_date_from_cron(self.outdated_cron_expression)
    
    def _delete_chunks_with_collection_switch(self, embedding_id: str) -> bool:
        try:
            original_collection = self.embedding_module.qdrant_manager.collection_name
            try:
                self.embedding_module.qdrant_manager.collection_name = settings.EMAIL_QA_COLLECTION
                return self.embedding_module.qdrant_manager.delete_chunks_by_embedding_id(embedding_id)
            except Exception as e:
                logger.error(f"Error deleting chunks for embedding_id {embedding_id}: {e}")
                return False
            finally:
                self.embedding_module.qdrant_manager.collection_name = original_collection
        except Exception as e:
            logger.error(f"Error in collection switching for embedding_id {embedding_id}: {e}")
            return False
    
    def _process_cleanup(self, cutoff_date: str) -> tuple[int, int]:
        try:
            threads_to_mark = self.metadata_db.get_threads_for_outdated_marking(cutoff_date)
            marked_count = 0
            
            for thread_record in threads_to_mark:
                if self.metadata_db.mark_thread_as_outdated(thread_record['thread_id']):
                    marked_count += 1
            
            if marked_count > 0:
                logger.info(f"Marked {marked_count} threads as outdated")
            
            outdated_threads = self.metadata_db.get_outdated_threads_with_embeddings()
            cleaned_count = 0
            
            for thread_record in outdated_threads:
                embedding_id = thread_record.get('embedding_id')
                if not embedding_id:
                    continue
                
                try:
                    if self._delete_chunks_with_collection_switch(embedding_id):
                        cleaned_count += 1
                except Exception as e:
                    logger.error(f"Error cleaning chunks for embedding_id {embedding_id}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up chunks for {cleaned_count} threads")
                
            return marked_count, cleaned_count
            
        except Exception as e:
            logger.error(f"Error in cleanup process: {e}")
            return 0, 0
    
    def _run_cleanup(self):
        if self.is_running:
            return
        
        self.is_running = True
        try:
            # Initialize embedding module if needed
            if not self.embedding_module:
                from backend.services.processing.rag.common.utils import initialize_embedding_module
                self.embedding_module = initialize_embedding_module(settings.EMAIL_QA_COLLECTION)
                if not self.embedding_module:
                    logger.error("Failed to initialize embedding module")
                    return
            
            cutoff_date = self._calculate_cutoff_date()
            marked_count, cleaned_count = self._process_cleanup(cutoff_date)
            
            if marked_count > 0 or cleaned_count > 0:
                logger.info(f"Cleanup complete: marked {marked_count}, cleaned {cleaned_count}")
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
        finally:
            self.is_running = False
    
    def _scheduler_loop(self):
        run_cron_scheduler(
            self.outdated_cron_expression,
            self._run_cleanup,
            "Gmail Cleanup Worker",
            None
        )
    
    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        
        self.is_scheduled = True
        self.worker_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Cleanup worker started")
    
    def stop(self):
        self.is_running = False
        self.is_scheduled = False
        logger.info("Cleanup worker stopped")
    
    def run_once(self):
        self._run_cleanup() 