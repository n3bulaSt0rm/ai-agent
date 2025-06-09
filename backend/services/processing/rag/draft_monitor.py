"""
Draft Monitor for Gmail API.
Simple draft management: check and delete existing drafts.
"""
import logging
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class EmailDraftMonitor:
    """
    Simple draft monitor for Gmail API.
    Provides draft checking and deletion functionality.
    """
    
    def __init__(self, service, metadata_db, user_id: str = 'me'):
        """
        Initialize draft monitor.
        
        Args:
            service: Gmail API service
            metadata_db: Database connection for checking existing drafts
            user_id: Gmail user ID (default: 'me')
        """
        self.service = service
        self.metadata_db = metadata_db
        self.user_id = user_id
        logger.info("Draft monitor initialized (DB check & API delete)")
    
    def track_draft(self, draft_id: str, thread_id: str) -> bool:
        """
        Track a newly created draft in the database.
        
        Args:
            draft_id: Gmail draft ID
            thread_id: Gmail thread ID
            
        Returns:
            True if successfully tracked, False otherwise
        """
        try:
            # Save draft tracking information using metadata_db
            success = self.metadata_db.save_gmail_draft_tracking(
                draft_id=draft_id,
                thread_id=thread_id
            )
            
            if success:
                logger.info(f"Successfully tracked draft {draft_id} for thread {thread_id}")
            else:
                logger.error(f"Failed to track draft {draft_id} for thread {thread_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error tracking draft {draft_id} for thread {thread_id}: {e}")
            return False

    def check_existing_draft(self, thread_id: str) -> Optional[str]:
        """
        Check if there's an existing draft for the thread in database and verify it exists on Gmail.
        
        Args:
            thread_id: Gmail thread ID
            
        Returns:
            Draft ID if found in database and exists on Gmail, None otherwise
        """
        try:
            # First check database for existing draft
            thread_info = self.metadata_db.get_gmail_thread_info(thread_id)
            
            if not thread_info or not thread_info.get('current_draft_id'):
                logger.debug(f"No existing draft found in database for thread {thread_id}")
                return None
            
            draft_id = thread_info['current_draft_id']
            logger.info(f"Found existing draft {draft_id} in database for thread {thread_id}")
            
            # Verify draft still exists on Gmail
            if self._verify_draft_exists_on_gmail(draft_id):
                logger.info(f"Draft {draft_id} verified to exist on Gmail for thread {thread_id}")
                return draft_id
            else:
                logger.info(f"Draft {draft_id} no longer exists on Gmail for thread {thread_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error checking existing draft for thread {thread_id}: {e}")
            return None
    
    def _verify_draft_exists_on_gmail(self, draft_id: str) -> bool:
        """
        Verify if a draft still exists on Gmail.
        
        Args:
            draft_id: Draft ID to verify
            
        Returns:
            True if draft exists on Gmail, False otherwise
        """
        try:
            self.service.users().drafts().get(
                userId=self.user_id,
                id=draft_id
            ).execute()
            
            logger.debug(f"Draft {draft_id} verified to exist on Gmail")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.debug(f"Draft {draft_id} not found on Gmail (404)")
                return False
            else:
                logger.error(f"Error verifying draft {draft_id} on Gmail: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error verifying draft {draft_id} on Gmail: {e}")
            return False
    
    def delete_draft(self, draft_id: str) -> bool:
        """
        Delete a draft by ID using Gmail API.
        
        Args:
            draft_id: Draft ID to delete
            
        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            self.service.users().drafts().delete(
                userId=self.user_id,
                id=draft_id
            ).execute()
            
            logger.info(f" Deleted draft {draft_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.info(f"Draft {draft_id} already deleted (404)")
                return True  
            else:
                logger.error(f"Error deleting draft {draft_id}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error deleting draft {draft_id}: {e}")
            return False 