"""
SQLite Persistence Layer for Security Blocks
Survives server restarts, supports IP blocking with expiry
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


# Default database path
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), 
    'security_blocks.db'
)


class SecurityPersistence:
    """
    SQLite-based persistence for security blocks and events.
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            # IP blocks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ip_blocks (
                    ip TEXT PRIMARY KEY,
                    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    reason TEXT,
                    attempt_count INTEGER DEFAULT 0
                )
            """)
            
            # Auth failures table (for tracking brute force)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT,
                    username TEXT,
                    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ip) REFERENCES ip_blocks(ip)
                )
            """)
            
            # Security events table (for audit trail)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT,
                    event_type TEXT,
                    details TEXT,
                    bpm REAL,
                    threat_score REAL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ip_blocks_expires 
                ON ip_blocks(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_auth_failures_ip 
                ON auth_failures(ip, failed_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_security_events_ip 
                ON security_events(ip, recorded_at)
            """)
    
    def persist_block(self, ip: str, duration_seconds: int, reason: str = "security_violation") -> None:
        """
        Persist an IP block to SQLite.
        
        Args:
            ip: IP address to block
            duration_seconds: Block duration in seconds
            reason: Reason for block
        """
        expires_at = datetime.utcnow() + timedelta(seconds=duration_seconds)
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ip_blocks (ip, blocked_at, expires_at, reason)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?)
            """, (ip, expires_at.isoformat(), reason))
    
    def is_ip_blocked(self, ip: str) -> bool:
        """
        Check if IP is currently blocked.
        
        Args:
            ip: IP address to check
            
        Returns:
            True if IP is blocked and not expired
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT expires_at FROM ip_blocks 
                WHERE ip = ? AND expires_at > CURRENT_TIMESTAMP
            """, (ip,))
            return cursor.fetchone() is not None
    
    def get_block_info(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        Get block information for an IP.
        
        Args:
            ip: IP address
            
        Returns:
            Dict with block info or None if not blocked
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT ip, blocked_at, expires_at, reason, attempt_count
                FROM ip_blocks 
                WHERE ip = ? AND expires_at > CURRENT_TIMESTAMP
            """, (ip,))
            row = cursor.fetchone()
            if row:
                return {
                    'ip': row['ip'],
                    'blocked_at': row['blocked_at'],
                    'expires_at': row['expires_at'],
                    'reason': row['reason'],
                    'attempt_count': row['attempt_count']
                }
            return None
    
    def record_auth_failure(self, ip: str, username: str = None) -> int:
        """
        Record a failed authentication attempt.
        
        Args:
            ip: IP address
            username: Optional username hint
            
        Returns:
            Count of failures in last hour for this IP
        """
        with self._get_connection() as conn:
            # Insert failure record with explicit timestamp
            now = datetime.utcnow().isoformat()
            conn.execute("""
                INSERT INTO auth_failures (ip, username, failed_at)
                VALUES (?, ?, ?)
            """, (ip, username, now))
            
            # Count failures in last hour
            one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            cursor = conn.execute("""
                SELECT COUNT(*) FROM auth_failures
                WHERE ip = ? AND failed_at > ?
            """, (ip, one_hour_ago))
            count = cursor.fetchone()[0]
            
            # Auto-block if threshold exceeded (10 per hour)
            if count >= 10:
                expires_at = (datetime.utcnow() + timedelta(seconds=3600)).isoformat()
                conn.execute("""
                    INSERT OR REPLACE INTO ip_blocks (ip, blocked_at, expires_at, reason, attempt_count)
                    VALUES (?, ?, ?, ?, ?)
                """, (ip, now, expires_at, "brute_force", count))
                
                # Log security event
                conn.execute("""
                    INSERT INTO security_events (ip, event_type, details, threat_score, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (ip, "BRUTE_FORCE", f"Blocked after {count} failed auth attempts", min(count / 10.0, 1.0), now))
            
            return count
    
    def clear_expired_blocks(self) -> int:
        """
        Clean up expired IP blocks.
        
        Returns:
            Number of expired blocks removed
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM ip_blocks
                WHERE expires_at < CURRENT_TIMESTAMP
            """)
            return cursor.rowcount
    
    def log_security_event(
        self, 
        ip: str, 
        event_type: str, 
        details: str = None,
        bpm: float = None,
        threat_score: float = None
    ) -> None:
        """
        Log a security event for audit trail.
        
        Args:
            ip: IP address
            event_type: Type of event (e.g., "BPM_INJECTION", "BRUTE_FORCE")
            details: Additional details
            bpm: BPM value if relevant
            threat_score: Calculated threat score
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO security_events (ip, event_type, details, bpm, threat_score)
                VALUES (?, ?, ?, ?, ?)
            """, (ip, event_type, details, bpm, threat_score))
    
    def get_recent_events(
        self, 
        ip: str = None, 
        event_type: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent security events.
        
        Args:
            ip: Filter by IP
            event_type: Filter by event type
            limit: Maximum results
            
        Returns:
            List of event dictionaries
        """
        with self._get_connection() as conn:
            query = "SELECT * FROM security_events WHERE 1=1"
            params = []
            
            if ip:
                query += " AND ip = ?"
                params.append(ip)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            
            query += " ORDER BY recorded_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    def get_auth_failure_count(self, ip: str, hours: int = 1) -> int:
        """
        Get count of auth failures for IP in last N hours.
        
        Args:
            ip: IP address
            hours: Time window
            
        Returns:
            Count of failures
        """
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM auth_failures
                WHERE ip = ? AND failed_at > ?
            """, (ip, since))
            return cursor.fetchone()[0]


# Global instance
_persistence: Optional[SecurityPersistence] = None


def get_persistence(db_path: str = None) -> SecurityPersistence:
    """
    Get or create global SecurityPersistence instance.
    
    Args:
        db_path: Optional custom database path
        
    Returns:
        SecurityPersistence instance
    """
    global _persistence
    if _persistence is None:
        _persistence = SecurityPersistence(db_path)
    return _persistence


def reset_persistence():
    """Reset global persistence instance (for testing)."""
    global _persistence
    _persistence = None
