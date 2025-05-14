import sqlite3
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from backend.core.config import settings

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
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                s3_url TEXT NOT NULL,
                upload_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                previous_status TEXT,
                pages INTEGER DEFAULT 0,
                description TEXT,
                file_created_at TEXT,
                updated_at TEXT,
                uploaded_by TEXT DEFAULT 'admin',
                metadata TEXT
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
    
    def add_pdf_file(self, filename: str, original_filename: str, file_size: int, 
                     file_type: str, s3_url: str, description: str = None, 
                     file_created_at: str = None, metadata: Dict[str, Any] = None) -> int:
        """
        Add a new file to the database.
        
        Args:
            filename: Stored filename
            original_filename: Original filename
            file_size: Size in bytes
            file_type: File type (e.g., 'application/pdf')
            s3_url: Amazon S3 URL
            description: File description
            file_created_at: When the file was created (if known)
            metadata: Additional metadata as dictionary
            
        Returns:
            ID of the new file record
        """
        now = datetime.now().isoformat()
        
        with self.conn:
            cursor = self.conn.execute(
                '''INSERT INTO files_management 
                   (filename, original_filename, file_size, file_type, s3_url, 
                    upload_at, description, file_created_at, updated_at, metadata, status) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (filename, original_filename, file_size, file_type, s3_url, 
                 now, description, file_created_at or now, now, json.dumps(metadata or {}), 'pending')
            )
            file_id = cursor.lastrowid
            
            return file_id
    
    def get_pdf_files(self, limit: int = 100, offset: int = 0, 
                      status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get a list of files with pagination and optional filtering.
        
        Args:
            limit: Maximum number of files to return
            offset: Offset for pagination
            status: Filter by status (pending, processing, processed, error, deleted)
            
        Returns:
            List of file records
        """
        query = 'SELECT * FROM files_management'
        params = []
        
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        elif status is None:
            # Exclude deleted files by default
            query += ' WHERE status != "deleted"'
        
        query += ' ORDER BY upload_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor = self.conn.execute(query, params)
        
        files = []
        for row in cursor:
            file_data = dict(row)
            if file_data.get('metadata'):
                file_data['metadata'] = json.loads(file_data['metadata'])
            files.append(file_data)
            
        return files
    
    def get_pdf_file_count(self, status: Optional[str] = None) -> int:
        """
        Get count of files, optionally filtered by status.
        
        Args:
            status: Filter by status
            
        Returns:
            Count of files
        """
        query = 'SELECT COUNT(*) FROM files_management'
        params = []
        
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        elif status is None:
            # Exclude deleted files by default
            query += ' WHERE status != "deleted"'
        
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
        if file_data.get('metadata'):
            file_data['metadata'] = json.loads(file_data['metadata'])
            
        return file_data
    
    def update_pdf_status(self, file_id: int, status: str, error: str = None, 
                         pages: int = None, previous_status: str = None) -> bool:
        """
        Update the status of a file.
        
        Args:
            file_id: ID of the file
            status: New status (pending, processing, processed, error, deleted)
            error: Error message if any
            pages: Number of pages in the document
            previous_status: Previous status before change (for restore operations)
            
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
        
        if error is not None:
            # Store error in metadata
            file = self.get_pdf_file(file_id)
            if file:
                metadata = file.get('metadata', {})
                metadata['error'] = error
                query_parts.append("metadata = ?")
                params.append(json.dumps(metadata))
        
        if pages is not None:
            query_parts.append("pages = ?")
            params.append(pages)
        
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
        Search for files by filename, description or content.
        
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
        WHERE (original_filename LIKE ? OR description LIKE ?)
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
            if file_data.get('metadata'):
                file_data['metadata'] = json.loads(file_data['metadata'])
            files.append(file_data)
            
        return files
    
    def get_pdf_file_by_uuid(self, file_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific file by UUID from metadata.
        
        Args:
            file_uuid: UUID of the file
            
        Returns:
            File record or None if not found
        """
        cursor = self.conn.execute(
            'SELECT * FROM files_management WHERE metadata LIKE ?', 
            (f'%"uuid": "{file_uuid}"%',)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        file_data = dict(row)
        if file_data.get('metadata'):
            file_data['metadata'] = json.loads(file_data['metadata'])
        
        return file_data
    
    def update_pdf_status_by_uuid(self, file_uuid: str, status: str) -> bool:
        """
        Update the status of a file by UUID.
        
        Args:
            file_uuid: UUID of the file
            status: New status (pending, processing, processed, error, deleted)
            
        Returns:
            True if successful, False otherwise
        """
        # First get the file by UUID to get its ID
        file = self.get_pdf_file_by_uuid(file_uuid)
        if not file:
            return False
        
        file_id = file['id']
        now = datetime.now().isoformat()
        
        try:
            with self.conn:
                # Update file status and updated_at timestamp
                self.conn.execute(
                    "UPDATE files_management SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, file_id)
                )
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