"""
SQLite database utilities for sandboxed migration testing
"""

import sqlite3
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager


class DatabaseSandbox:
    """Isolated SQLite environment for testing migrations"""
    
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.connection: Optional[sqlite3.Connection] = None
        
    def connect(self):
        """Initialize in-memory database"""
        self.connection = sqlite3.connect(
            ":memory:",
            timeout=self.timeout,
            isolation_level=None,  # Autocommit mode for simplicity
            check_same_thread=False
        )
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")
        # Return rows as dictionaries
        self.connection.row_factory = sqlite3.Row
        return self
    
    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def execute_script(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        Execute multi-statement SQL script
        Returns: (success, error_message)
        """
        if not self.connection:
            raise RuntimeError("Database not connected")
        
        try:
            self.connection.executescript(sql)
            return True, None
        except sqlite3.Error as e:
            return False, str(e)
    
    def execute_query(self, sql: str) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """
        Execute single SELECT query
        Returns: (success, rows, error_message)
        """
        if not self.connection:
            raise RuntimeError("Database not connected")
        
        try:
            cursor = self.connection.execute(sql)
            rows = [dict(row) for row in cursor.fetchall()]
            return True, rows, None
        except sqlite3.Error as e:
            return False, [], str(e)
    
    def get_schema_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Extract schema information for a table"""
        if not self.connection:
            return None
        
        try:
            # Get columns
            cursor = self.connection.execute(
                f"PRAGMA table_info({table_name})"
            )
            columns = [dict(row) for row in cursor.fetchall()]
            
            # Get indexes
            cursor = self.connection.execute(
                f"PRAGMA index_list({table_name})"
            )
            indexes = [dict(row) for row in cursor.fetchall()]
            
            # Get foreign keys
            cursor = self.connection.execute(
                f"PRAGMA foreign_key_list({table_name})"
            )
            foreign_keys = [dict(row) for row in cursor.fetchall()]
            
            return {
                "table_name": table_name,
                "columns": columns,
                "indexes": indexes,
                "foreign_keys": foreign_keys
            }
        except sqlite3.Error:
            return None
    
    def get_sample_data(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample rows from table"""
        success, rows, _ = self.execute_query(
            f"SELECT * FROM {table_name} LIMIT {limit}"
        )
        return rows if success else []
    
    def compute_hash(self) -> str:
        """
        Compute hash of all user tables for corruption detection
        Critical for HARD mode (silent corruption detection)
        """
        if not self.connection:
            return ""
        
        try:
            # Get all table names
            cursor = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            # Hash table contents
            hasher = hashlib.sha256()
            for table in sorted(tables):
                success, rows, _ = self.execute_query(f"SELECT * FROM {table} ORDER BY rowid")
                if success:
                    hasher.update(json.dumps(rows, sort_keys=True).encode())
            
            return hasher.hexdigest()
        except sqlite3.Error:
            return ""
    
    def get_table_names(self) -> List[str]:
        """Get all user table names"""
        if not self.connection:
            return []
        
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]


@contextmanager
def sandbox_db():
    """Context manager for database sandbox"""
    db = DatabaseSandbox().connect()
    try:
        yield db
    finally:
        db.close()
