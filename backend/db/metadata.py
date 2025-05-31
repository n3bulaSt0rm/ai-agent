import sqlite3
import os
import json
import hashlib
from datetime import datetime
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
                object_url TEXT,
                s3_uri TEXT NOT NULL,
                upload_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                previous_status TEXT,
                pages INTEGER DEFAULT 0,
                keywords TEXT,
                pages_processed_range TEXT,
                description TEXT,
                file_created_at TEXT,
                updated_at TEXT,
                uploaded_by TEXT DEFAULT 'admin'
            )
            ''')
            
            # Users table
            self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                email TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            ''')
            
            # Create default admin user if not exists
            cursor = self.conn.execute("SELECT * FROM users WHERE username = ?", (settings.ADMIN_USERNAME,))
            if not cursor.fetchone():
                # Hash the password
                password_hash = hashlib.sha256(settings.ADMIN_PASSWORD.encode()).hexdigest()
                
                self.conn.execute(
                    '''INSERT INTO users 
                       (username, password_hash, role, created_at) 
                       VALUES (?, ?, ?, ?)''',
                    (settings.ADMIN_USERNAME, password_hash, 'admin', datetime.now().isoformat())
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
            # Hash the provided password
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            # Query the user
            cursor = self.conn.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1", 
                (username,)
            )
            user = cursor.fetchone()
            
            if not user:
                return False, None
                
            user_data = dict(user)
            
            # Check if password matches
            if user_data['password_hash'] == password_hash:
                # Update last login time
                with self.conn:
                    self.conn.execute(
                        "UPDATE users SET last_login = ? WHERE id = ?",
                        (datetime.now().isoformat(), user_data['id'])
                    )
                
                # Remove password hash from returned data
                user_data.pop('password_hash', None)
                
                return True, user_data
            
            return False, None
        except Exception as e:
            print(f"Error verifying user: {e}")
            return False, None
    
    def add_pdf_file(self, filename: str, file_size: int, 
                     content_type: str, s3_uri: str, object_url: str = None, description: str = None, 
                     file_created_at: str = None, pages: int = 0, uuid: str = None, keywords: str = None) -> int:
        """
        Add a new file to the database.
        
        Args:
            filename: Original filename
            file_size: Size in bytes
            content_type: File content type (e.g., 'application/pdf')
            s3_uri: Amazon S3 URI
            object_url: Public URL for the file
            description: File description
            file_created_at: When the file was created (if known)
            pages: Number of pages in the document
            uuid: Unique identifier for the file
            keywords: JSON string containing keywords
            
        Returns:
            ID of the new file record
        """
        now = datetime.now().isoformat()
        
        # Generate UUID if not provided
        if not uuid:
            uuid = str(uuid4())
            
        with self.conn:
            cursor = self.conn.execute(
                '''INSERT INTO files_management 
                   (uuid, filename, file_size, content_type, s3_uri, object_url,
                    upload_at, description, file_created_at, updated_at, pages, status, keywords) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (uuid, filename, file_size, content_type, s3_uri, object_url,
                 now, description, file_created_at or now, now, pages, 'pending', keywords)
            )
            file_id = cursor.lastrowid
            
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
        
        cursor = self.conn.execute(query, params)
        
        files = []
        for row in cursor:
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
        
        cursor = self.conn.execute(query, params)
        return cursor.fetchone()[0]
    
    def get_pdf_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific file by ID.
        
        Args:
            file_id: ID of the file
            
        Returns:
            File record or None if not found
        """
        cursor = self.conn.execute('SELECT * FROM files_management WHERE id = ?', (file_id,))
        row = cursor.fetchone()
        
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
        
        cursor = self.conn.execute(sql_query, tuple(params))
        
        files = []
        for row in cursor:
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
        cursor = self.conn.execute(
            'SELECT * FROM files_management WHERE uuid = ?', 
            (file_uuid,)
        )
        row = cursor.fetchone()
        
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

# Singleton instance
_metadata_db = None

def get_metadata_db() -> MetadataDB:
    """Get the metadata database instance."""
    global _metadata_db
    if _metadata_db is None:
        _metadata_db = MetadataDB()
    return _metadata_db 