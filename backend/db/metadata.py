import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from backend.core.config import settings
from uuid import uuid4

class MetadataDB:
    """Database class for handling file metadata"""
    
    def __init__(self, db_path: str = None):
        """Initialize database connection and ensure tables exist."""
        self.db_path = db_path or settings.DATABASE_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        """Create necessary tables if they don't exist."""
        with self.conn:
            # Files management table
            self.conn.execute('''
            CREATE TABLE IF NOT EXISTS files_management (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                object_url TEXT NOT NULL,
                upload_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                previous_status TEXT,
                pages INTEGER DEFAULT 0,
                keywords TEXT,
                pages_processed_range TEXT,
                description TEXT,
                file_created_at TEXT,
                updated_at TEXT,
                uploaded_by TEXT
            )
            ''')
            
            # Users table
            self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                uuid TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                updated_by TEXT,
                is_banned INTEGER DEFAULT 0
            )
            ''')
            
            # Check if columns exist, add them if not
            cursor = self.conn.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'updated_at' not in columns:
                self.conn.execute('ALTER TABLE users ADD COLUMN updated_at TEXT')
            
            if 'updated_by' not in columns:
                self.conn.execute('ALTER TABLE users ADD COLUMN updated_by TEXT')
                
            if 'is_banned' not in columns:
                self.conn.execute('ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0')
            
            self.conn.execute('''
            CREATE TABLE IF NOT EXISTS gmail_threads (
                thread_id TEXT PRIMARY KEY,
                context_summary TEXT,
                current_draft_id TEXT,
                last_processed_message_id TEXT,
                embedding_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_outdated INTEGER DEFAULT 0
            )
            ''')
            
            # Check if is_outdated column exists, add it if not
            cursor = self.conn.execute("PRAGMA table_info(gmail_threads)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'is_outdated' not in columns:
                self.conn.execute('ALTER TABLE gmail_threads ADD COLUMN is_outdated INTEGER DEFAULT 0')
            
            # Create default admin user if not exists
            result = self.conn.execute("SELECT * FROM users WHERE username = ?", (settings.ADMIN_USERNAME,))
            if not result.fetchone():
                admin_uuid = str(uuid4())
                now = datetime.now().isoformat()
                self.conn.execute(
                    '''INSERT INTO users 
                       (uuid, username, password, role, created_at, updated_at, updated_by) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (admin_uuid, settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD, 'admin', now, now, 'system')
                )
    
    def verify_user(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify user credentials.
        
        Args:
            username: Username to verify
            password: Password to verify
            
        Returns:
            Tuple of (authenticated, user_data)
        """
        try:
            # Query the user
            result = self.conn.execute(
                "SELECT * FROM users WHERE username = ?", 
                (username,)
            )
            user = result.fetchone()
            
            if not user:
                return False, None
                
            user_data = dict(user)
            
            # Check if user is banned
            if user_data.get('is_banned', 0) == 1:
                return False, None
            
            # Check if password matches (direct comparison for simplicity)
            if user_data['password'] == password:
                # Remove password from returned data
                user_data.pop('password', None)
                
                return True, user_data
            
            return False, None
        except Exception as e:
            print(f"Error verifying user: {e}")
            return False, None
    
    def create_or_get_google_user(self, email: str) -> Dict[str, Any]:
        """
        Create a new user from Google OAuth or get existing user.
        
        Args:
            email: User's email from Google OAuth
            
        Returns:
            User data dict
        """
        try:
            # Check if user exists
            result = self.conn.execute(
                "SELECT * FROM users WHERE username = ?", 
                (email,)
            )
            user = result.fetchone()
            
            if user:
                # User exists, check if banned
                user_data = dict(user)
                if user_data.get('is_banned', 0) == 1:
                    raise Exception(f"User {email} is banned")
                
                user_data.pop('password', None)
                return user_data
            
            # Create new user
            user_uuid = str(uuid4())
            now = datetime.now().isoformat()
            
            with self.conn:
                self.conn.execute(
                    '''INSERT INTO users 
                       (uuid, username, password, role, created_at, updated_at, updated_by) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (user_uuid, email, '', 'user', now, now, '')  
                )
                
                # Get the created user
                result = self.conn.execute(
                    "SELECT * FROM users WHERE username = ?", 
                    (email,)
                )
                user = result.fetchone()
                user_data = dict(user)
                user_data.pop('password', None)
                
                print(f"Created new Google user: {email}")
                return user_data
                
        except Exception as e:
            print(f"Error creating/getting Google user: {e}")
            raise
    
    def get_all_users(self, limit: int = 100, offset: int = 0, search_query: str = None) -> List[Dict[str, Any]]:
        """
        Get all users with pagination and optional search.
        
        Args:
            limit: Maximum number of users to return
            offset: Offset for pagination
            search_query: Search query for username
            
        Returns:
            List of user records (without passwords)
        """
        try:
            query = "SELECT uuid, username, role, created_at, updated_at, updated_by FROM users"
            params = []
            
            if search_query:
                query += " WHERE username LIKE ?"
                params.append(f"%{search_query}%")
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            result = self.conn.execute(query, params)
            
            users = []
            for row in result:
                user_data = dict(row)
                users.append(user_data)
                
            return users
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []
    
    def get_users_count(self, search_query: str = None) -> int:
        """
        Get total count of users.
        
        Args:
            search_query: Search query for username
            
        Returns:
            Count of users
        """
        try:
            query = "SELECT COUNT(*) FROM users"
            params = []
            
            if search_query:
                query += " WHERE username LIKE ?"
                params.append(f"%{search_query}%")
            
            result = self.conn.execute(query, params)
            return result.fetchone()[0]
        except Exception as e:
            print(f"Error getting users count: {e}")
            return 0
    
    def update_user_role(self, user_uuid: str, new_role: str, updated_by: str) -> bool:
        """
        Update user role.
        
        Args:
            user_uuid: UUID of the user
            new_role: New role ('admin', 'manager', or 'user')
            updated_by: Username of who made the update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if new_role not in ['admin', 'manager', 'user']:
                return False
                
            now = datetime.now().isoformat()
            
            with self.conn:
                self.conn.execute(
                    "UPDATE users SET role = ?, updated_at = ?, updated_by = ? WHERE uuid = ?",
                    (new_role, now, updated_by, user_uuid)
                )
            
            print(f"Updated user {user_uuid} role to {new_role} by {updated_by}")
            return True
        except Exception as e:
            print(f"Error updating user role: {e}")
            return False
    
    def ban_user(self, user_uuid: str, banned_by: str) -> bool:
        """
        Ban a user.
        
        Args:
            user_uuid: UUID of the user to ban
            banned_by: Username of who performed the ban
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if user exists and is not the default admin
            result = self.conn.execute("SELECT username FROM users WHERE uuid = ?", (user_uuid,))
            user = result.fetchone()
            
            if not user:
                return False
            
            # Prevent banning of default admin
            if user['username'] == settings.ADMIN_USERNAME:
                print(f"Cannot ban default admin user: {settings.ADMIN_USERNAME}")
                return False
            
            now = datetime.now().isoformat()
            
            with self.conn:
                self.conn.execute(
                    "UPDATE users SET is_banned = 1, updated_at = ?, updated_by = ? WHERE uuid = ?",
                    (now, banned_by, user_uuid)
                )
            
            print(f"Banned user {user_uuid} ({user['username']}) by {banned_by}")
            return True
        except Exception as e:
            print(f"Error banning user: {e}")
            return False
    
    def unban_user(self, user_uuid: str, unbanned_by: str) -> bool:
        """
        Unban a user.
        
        Args:
            user_uuid: UUID of the user to unban
            unbanned_by: Username of who performed the unban
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if user exists
            result = self.conn.execute("SELECT username FROM users WHERE uuid = ?", (user_uuid,))
            user = result.fetchone()
            
            if not user:
                return False
            
            now = datetime.now().isoformat()
            
            with self.conn:
                self.conn.execute(
                    "UPDATE users SET is_banned = 0, updated_at = ?, updated_by = ? WHERE uuid = ?",
                    (now, unbanned_by, user_uuid)
                )
            
            print(f"Unbanned user {user_uuid} ({user['username']}) by {unbanned_by}")
            return True
        except Exception as e:
            print(f"Error unbanning user: {e}")
            return False
    
    def get_user_by_uuid(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by UUID.
        
        Args:
            user_uuid: UUID of the user
            
        Returns:
            User data dict (without password) or None if not found
        """
        try:
            result = self.conn.execute(
                "SELECT uuid, username, role, created_at, updated_at, updated_by, is_banned FROM users WHERE uuid = ?", 
                (user_uuid,)
            )
            user = result.fetchone()
            
            if user:
                return dict(user)
            return None
        except Exception as e:
            print(f"Error getting user by UUID: {e}")
            return None
    
    def add_pdf_file(self, filename: str, file_size: int, 
                     content_type: str, object_url: str, description: str = None, 
                     file_created_at: str = None, pages: int = 0, uuid: str = None, keywords: str = None,
                     uploaded_by: str = None) -> int:
        """
        Add a new file to the database.
        
        Args:
            filename: Original filename
            file_size: Size in bytes
            content_type: File content type (e.g., 'application/pdf')
            object_url: Public URL for the file
            description: File description
            file_created_at: When the file was created (if known)
            pages: Number of pages in the document
            uuid: Unique identifier for the file
            keywords: JSON string containing keywords
            uploaded_by: Username of the user who uploaded the file
            
        Returns:
            ID of the new file record
        """
        now = datetime.now().isoformat()
        
        # Generate UUID if not provided
        if not uuid:
            uuid = str(uuid4())
            
        with self.conn:
            result = self.conn.execute(
                '''INSERT INTO files_management 
                   (uuid, filename, file_size, content_type, object_url,
                    upload_at, description, file_created_at, updated_at, pages, status, keywords, uploaded_by) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (uuid, filename, file_size, content_type, object_url,
                 now, description, file_created_at or now, now, pages, 'pending', keywords, uploaded_by)
            )
            file_id = result.lastrowid
            
            return file_id
    
    def get_pdf_files(self, limit: int = 100, offset: int = 0, 
                      status: Optional[str] = None, exclude_status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get a list of files with pagination and optional filtering.
        
        Args:
            limit: Maximum number of files to return
            offset: Offset for pagination
            status: Filter by status (pending, processing, processed, error, deleted)
            exclude_status: Exclude files with this status
            
        Returns:
            List of file records
        """
        query = 'SELECT * FROM files_management'
        params = []
        
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        elif exclude_status:
            query += ' WHERE status != ?'
            params.append(exclude_status)
        
        query += ' ORDER BY upload_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        result = self.conn.execute(query, params)
        
        files = []
        for row in result:
            file_data = dict(row)
            files.append(file_data)
            
        return files
    
    def get_pdf_file_count(self, status: Optional[str] = None, exclude_status: Optional[str] = None) -> int:
        """
        Get count of files, optionally filtered by status.
        
        Args:
            status: Filter by status
            exclude_status: Exclude files with this status
            
        Returns:
            Count of files
        """
        query = 'SELECT COUNT(*) FROM files_management'
        params = []
        
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        elif exclude_status:
            query += ' WHERE status != ?'
            params.append(exclude_status)
        
        result = self.conn.execute(query, params)
        return result.fetchone()[0]
    
    def get_pdf_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific file by ID.
        
        Args:
            file_id: ID of the file
            
        Returns:
            File record or None if not found
        """
        result = self.conn.execute('SELECT * FROM files_management WHERE id = ?', (file_id,))
        row = result.fetchone()
        
        if not row:
            return None
            
        file_data = dict(row)
        return file_data
    
    def update_pdf_status(self, file_id: int, status: str, error: str = None, 
                         pages: int = None, previous_status: str = None, pages_processed_range: str = None) -> bool:
        """
        Update the status of a file.
        
        Args:
            file_id: ID of the file
            status: New status (pending, processing, processed, error, deleted)
            error: Error message if any
            pages: Number of pages in the document
            previous_status: Previous status before change (for restore operations)
            pages_processed_range: Range of pages processed in JSON format
            
        Returns:
            True if successful, False otherwise
        """
        now = datetime.now().isoformat()
        params = []
        query_parts = []
        
        # Build query dynamically based on provided parameters
        query_parts.append("status = ?")
        params.append(status)
        
        query_parts.append("updated_at = ?")
        params.append(now)
        
        # If we're changing to deleted status, save the current status
        if status == "deleted" and previous_status:
            query_parts.append("previous_status = ?")
            params.append(previous_status)
        
        if pages is not None:
            query_parts.append("pages = ?")
            params.append(pages)
            
        if pages_processed_range is not None:
            query_parts.append("pages_processed_range = ?")
            params.append(pages_processed_range)
        
        # Complete the query
        query = f"UPDATE files_management SET {', '.join(query_parts)} WHERE id = ?"
        params.append(file_id)
        
        try:
            with self.conn:
                # Update file status
                self.conn.execute(query, params)
            return True
        except Exception as e:
            print(f"Error updating file status: {e}")
            return False
            
    def search_pdf_files(self, query: str, limit: int = 10, offset: int = 0, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for files by filename or description.
        
        Args:
            query: Search query
            limit: Maximum number of files to return
            offset: Offset for pagination
            status: Filter by status or None for non-deleted files, 'deleted' for trash, 'all' for all files
            
        Returns:
            List of file records matching the query
        """
        search_term = f"%{query}%"
        
        # Base query parameters
        params = [search_term, search_term]
        
        # Construct SQL query based on status
        sql_query = '''
        SELECT * FROM files_management
        WHERE (filename LIKE ? OR description LIKE ?)
        '''
        
        # Add status filtering
        if status == 'deleted':
            sql_query += "AND status = 'deleted'"
        elif status == 'all':
            # Don't add any status filter
            pass
        else:
            # By default, exclude deleted files
            sql_query += "AND status != 'deleted'"
        
        # Add order and pagination
        sql_query += '''
        ORDER BY upload_at DESC
        LIMIT ? OFFSET ?
        '''
        
        params.extend([limit, offset])
        
        result = self.conn.execute(sql_query, tuple(params))
        
        files = []
        for row in result:
            file_data = dict(row)
            files.append(file_data)
            
        return files
    
    def get_pdf_file_by_uuid(self, file_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific file by UUID.
        
        Args:
            file_uuid: UUID of the file
            
        Returns:
            File record or None if not found
        """
        result = self.conn.execute(
            'SELECT * FROM files_management WHERE uuid = ?', 
            (file_uuid,)
        )
        row = result.fetchone()
        
        if not row:
            return None
        
        file_data = dict(row)
        return file_data
    
    def update_pdf_status_by_uuid(self, file_uuid: str, status: str, pages: int = None, pages_processed_range: str = None) -> bool:
        """
        Update the status of a file by UUID.
        
        Args:
            file_uuid: UUID of the file
            status: New status (pending, processing, processed, error, deleted)
            pages: Number of pages if available
            pages_processed_range: Range of pages processed in JSON format
            
        Returns:
            True if successful, False otherwise
        """
        now = datetime.now().isoformat()
        
        try:
            with self.conn:
                query = "UPDATE files_management SET status = ?, updated_at = ?"
                params = [status, now]
                
                if pages is not None:
                    query += ", pages = ?"
                    params.append(pages)
                
                if pages_processed_range is not None:
                    query += ", pages_processed_range = ?"
                    params.append(pages_processed_range)
                    
                query += " WHERE uuid = ?"
                params.append(file_uuid)
                
                # Update file status
                self.conn.execute(query, params)
            return True
        except Exception as e:
            print(f"Error updating file status by UUID: {e}")
            return False
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    # Gmail-related methods
    
    def get_gmail_thread_info(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Gmail thread info from unified table.
        
        Args:
            thread_id: Gmail thread ID
            
        Returns:
            Thread info or None if not exists
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads WHERE thread_id = ?
            ''', (thread_id,))
            
            row = result.fetchone()
            
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            print(f"Error getting Gmail thread info: {e}")
            return None
    
    def upsert_gmail_thread(self, thread_id: str, context_summary: str = None, 
                           current_draft_id: str = None,
                           last_processed_message_id: str = None,
                           embedding_id: str = None) -> bool:
        """
        Upsert Gmail thread info in unified table.
        
        Args:
            thread_id: Gmail thread ID
            context_summary: Context summary
            current_draft_id: Current draft ID
            last_processed_message_id: Last processed message ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.now().isoformat()
            
            with self.conn:
                # Check if thread exists
                result = self.conn.execute('SELECT * FROM gmail_threads WHERE thread_id = ?', (thread_id,))
                existing = result.fetchone()
                
                if existing:
                    # Update existing
                    update_fields = []
                    params = []
                    
                    if context_summary is not None:
                        update_fields.append('context_summary = ?')
                        params.append(context_summary)
                    if current_draft_id is not None:
                        update_fields.append('current_draft_id = ?')
                        params.append(current_draft_id)
                    if last_processed_message_id is not None:
                        update_fields.append('last_processed_message_id = ?')
                        params.append(last_processed_message_id)
                    if embedding_id is not None:
                        update_fields.append('embedding_id = ?')
                        params.append(embedding_id)
                    
                    update_fields.append('updated_at = ?')
                    params.append(now)
                    params.append(thread_id)
                    
                    query = f"UPDATE gmail_threads SET {', '.join(update_fields)} WHERE thread_id = ?"
                    self.conn.execute(query, params)
                else:
                    # Insert new
                    self.conn.execute('''
                        INSERT INTO gmail_threads 
                        (thread_id, context_summary, current_draft_id, 
                         last_processed_message_id, embedding_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (thread_id, context_summary, current_draft_id, 
                          last_processed_message_id, embedding_id, now, now))
            
            print(f"Upserted Gmail thread for {thread_id}")
            return True
            
        except Exception as e:
            print(f"Error upserting Gmail thread: {e}")
            return False
    
    def get_gmail_thread_summaries(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get list of Gmail threads with context summaries.
        
        Args:
            limit: Maximum number of summaries to return
            offset: Offset for pagination
            
        Returns:
            List of thread records with summaries
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads 
                WHERE context_summary IS NOT NULL
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            summaries = []
            for row in result:
                summary_data = dict(row)
                summaries.append(summary_data)
                
            return summaries
            
        except Exception as e:
            print(f"Error getting Gmail thread summaries: {e}")
            return []

    # Gmail Draft Tracking Methods
    
    def save_gmail_thread_summary(self, thread_id: str, summary: str) -> bool:
        """
        Save Gmail thread summary to unified threads table.
        
        Args:
            thread_id: Gmail thread ID
            summary: Thread summary content
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.upsert_gmail_thread(
                thread_id=thread_id,
                context_summary=summary
            )
            
        except Exception as e:
            print(f"Error saving Gmail thread summary: {e}")
            return False
    
    def save_gmail_draft_tracking(self, draft_id: str, thread_id: str) -> bool:
        """
        Save Gmail draft tracking information to unified threads table.
        
        Args:
            draft_id: Gmail draft ID
            thread_id: Thread ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.upsert_gmail_thread(
                thread_id=thread_id,
                current_draft_id=draft_id
            )
            
        except Exception as e:
            print(f"Error saving Gmail draft tracking: {e}")
            return False
    

    
    def get_gmail_draft_tracking(self, draft_id: str = None) -> List[Dict[str, Any]]:
        """
        Get Gmail thread records with draft information.
        
        Args:
            draft_id: Specific draft ID to get (optional)
            
        Returns:
            List of thread records with draft info
        """
        try:
            query = 'SELECT * FROM gmail_threads WHERE current_draft_id IS NOT NULL'
            params = []
            
            if draft_id:
                query += ' AND current_draft_id = ?'
                params.append(draft_id)
            
            query += ' ORDER BY updated_at DESC'
            
            result = self.conn.execute(query, params)
            
            # Return simplified thread records (no mapping needed)
            threads = []
            for row in result:
                thread_data = dict(row)
                threads.append(thread_data)
                
            return threads
            
        except Exception as e:
            print(f"Error getting Gmail draft tracking: {e}")
            return []
    
    def delete_gmail_draft_tracking(self, draft_id: str) -> bool:
        """
        Clear draft info from thread record.
        
        Args:
            draft_id: Gmail draft ID to clear
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.conn:
                self.conn.execute('''
                    UPDATE gmail_threads 
                    SET current_draft_id = NULL, updated_at = ?
                    WHERE current_draft_id = ?
                ''', (datetime.now().isoformat(), draft_id))
            
            print(f"Cleared draft tracking for {draft_id}")
            return True
            
        except Exception as e:
            print(f"Error clearing Gmail draft tracking: {e}")
            return False
    
    def cleanup_old_gmail_drafts(self, days: int = 7) -> bool:
        """
        Clean up old thread records with completed status.
        
        Args:
            days: Keep records newer than this many days
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            with self.conn:
                result = self.conn.execute('''
                    UPDATE gmail_threads 
                    SET current_draft_id = NULL
                    WHERE updated_at < ? AND current_draft_id IS NOT NULL
                ''', (cutoff_date,))
                
                cleaned_count = result.rowcount
                
            print(f"Cleaned up {cleaned_count} old draft records")
            return True
            
        except Exception as e:
            print(f"Error cleaning up old Gmail drafts: {e}")
            return False
    
    def get_thread_by_draft_id(self, draft_id: str) -> Dict[str, Any]:
        """
        Get thread info by draft ID.
        
        Args:
            draft_id: Gmail draft ID
            
        Returns:
            Thread record dict or None if not found
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads WHERE current_draft_id = ?
            ''', (draft_id,))
            
            row = result.fetchone()
            return dict(row) if row else None
            
        except Exception as e:
            print(f"Error getting thread by draft ID: {e}")
            return None

    def get_threads_to_process(self, cutoff_date: str = None) -> List[Dict[str, Any]]:
        """
        Get threads that need processing - only non-outdated threads.
        
        Args:
            cutoff_date: ISO format cutoff date string (optional, for backward compatibility)
            
        Returns:
            List of thread records that need processing
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads 
                WHERE (is_outdated IS NULL OR is_outdated != 1)
                AND (
                    embedding_id IS NULL 
                    OR embedding_id != (thread_id || ',' || COALESCE(last_processed_message_id, ''))
                )
                ORDER BY updated_at DESC
            ''')
            
            threads = []
            for row in result:
                thread_data = dict(row)
                threads.append(thread_data)
            
            print(f"Found {len(threads)} non-outdated threads to process")
            return threads
            
        except Exception as e:
            print(f"Error getting threads to process: {e}")
            return []
    
    def get_threads_for_cleanup(self, cutoff_date: str) -> List[Dict[str, Any]]:
        """
        Get threads that should be cleaned up based on cutoff date.
        
        Args:
            cutoff_date: ISO format cutoff date string
            
        Returns:
            List of thread records that should be cleaned up
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads 
                WHERE updated_at < ?
                AND embedding_id IS NOT NULL
                ORDER BY updated_at ASC
            ''', (cutoff_date,))
            
            threads = []
            for row in result:
                thread_data = dict(row)
                threads.append(thread_data)
            
            print(f"Found {len(threads)} threads for cleanup (older than {cutoff_date})")
            return threads
            
        except Exception as e:
            print(f"Error getting threads for cleanup: {e}")
            return []

    def get_threads_for_outdated_marking(self, cutoff_date: str) -> List[Dict[str, Any]]:
        """
        Get threads that should be marked as outdated based on cutoff date.
        
        Args:
            cutoff_date: ISO format cutoff date string
            
        Returns:
            List of thread records that should be marked as outdated
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads 
                WHERE updated_at < ?
                AND (is_outdated IS NULL OR is_outdated != 1)
                AND embedding_id IS NOT NULL
                ORDER BY updated_at ASC
            ''', (cutoff_date,))
            
            threads = []
            for row in result:
                thread_data = dict(row)
                threads.append(thread_data)
            
            print(f"Found {len(threads)} threads to mark as outdated (older than {cutoff_date})")
            return threads
            
        except Exception as e:
            print(f"Error getting threads for outdated marking: {e}")
            return []

    def mark_thread_as_outdated(self, thread_id: str) -> bool:
        """
        Mark a thread as outdated.
        
        Args:
            thread_id: Gmail thread ID to mark as outdated
            
        Returns:
            True if successful, False otherwise
        """
        try:
            now = datetime.now().isoformat()
            
            with self.conn:
                self.conn.execute('''
                    UPDATE gmail_threads 
                    SET is_outdated = 1, updated_at = ?
                    WHERE thread_id = ?
                ''', (now, thread_id))
            
            print(f"Marked thread {thread_id} as outdated")
            return True
            
        except Exception as e:
            print(f"Error marking thread as outdated: {e}")
            return False

    def get_outdated_threads_with_embeddings(self) -> List[Dict[str, Any]]:
        """
        Get threads that are marked as outdated and have embedding_id.
        
        Returns:
            List of outdated thread records with embedding_id
        """
        try:
            result = self.conn.execute('''
                SELECT * FROM gmail_threads 
                WHERE is_outdated = 1
                AND embedding_id IS NOT NULL
                ORDER BY updated_at ASC
            ''')
            
            threads = []
            for row in result:
                thread_data = dict(row)
                threads.append(thread_data)
            
            print(f"Found {len(threads)} outdated threads with embeddings")
            return threads
            
        except Exception as e:
            print(f"Error getting outdated threads: {e}")
            return []

    def get_all_users_advanced(self, limit: int = 100, offset: int = 0, search_query: str = None, 
                              sort_by: str = None, sort_order: str = "desc", date_filter: str = None) -> List[Dict[str, Any]]:
        """
        Get all users with advanced filtering, sorting and pagination.
        Excludes the default admin user (username='admin').
        
        Args:
            limit: Maximum number of users to return
            offset: Offset for pagination
            search_query: Search query for username
            sort_by: Field to sort by (username, role, created_at)
            sort_order: Sort order (asc, desc)
            date_filter: Filter by creation date (YYYY-MM-DD)
            
        Returns:
            List of user records (without passwords)
        """
        try:
            query = "SELECT uuid, username, role, created_at, updated_at, updated_by, is_banned FROM users"
            params = []
            where_conditions = []
            
            # Always exclude the default admin user
            where_conditions.append("username != ?")
            params.append(settings.ADMIN_USERNAME)
            
            # Add search condition
            if search_query:
                where_conditions.append("username LIKE ?")
                params.append(f"%{search_query}%")
            
            # Add date filter condition
            if date_filter:
                where_conditions.append("DATE(created_at) = ?")
                params.append(date_filter)
            
            # Add WHERE clause
            query += " WHERE " + " AND ".join(where_conditions)
            
            # Add sorting
            valid_sort_fields = ["username", "role", "created_at", "updated_at"]
            if sort_by and sort_by in valid_sort_fields:
                order_direction = "ASC" if sort_order.lower() == "asc" else "DESC"
                query += f" ORDER BY {sort_by} {order_direction}"
            else:
                query += " ORDER BY created_at DESC"  # Default sort
            
            # Add pagination
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            result = self.conn.execute(query, params)
            
            users = []
            for row in result:
                user_data = dict(row)
                users.append(user_data)
                
            return users
        except Exception as e:
            print(f"Error getting users with advanced options: {e}")
            return []
    
    def get_users_count_advanced(self, search_query: str = None, date_filter: str = None) -> int:
        """
        Get total count of users with filtering.
        Excludes the default admin user (username='admin').
        
        Args:
            search_query: Search query for username
            date_filter: Filter by creation date (YYYY-MM-DD)
            
        Returns:
            Count of users
        """
        try:
            query = "SELECT COUNT(*) FROM users"
            params = []
            where_conditions = []
            
            # Always exclude the default admin user
            where_conditions.append("username != ?")
            params.append(settings.ADMIN_USERNAME)
            
            # Add search condition
            if search_query:
                where_conditions.append("username LIKE ?")
                params.append(f"%{search_query}%")
            
            # Add date filter condition
            if date_filter:
                where_conditions.append("DATE(created_at) = ?")
                params.append(date_filter)
            
            # Add WHERE clause
            query += " WHERE " + " AND ".join(where_conditions)
            
            result = self.conn.execute(query, params)
            return result.fetchone()[0]
        except Exception as e:
            print(f"Error getting users count with advanced options: {e}")
            return 0

_metadata_db = None

def get_metadata_db() -> MetadataDB:
    """Get the metadata database instance."""
    global _metadata_db
    if _metadata_db is None:
        _metadata_db = MetadataDB()
    return _metadata_db 