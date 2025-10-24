"""
Feedback Database Module
Manages persistent storage of user feedback for ML pipeline optimization
"""

import sqlite3
import json
import time
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class FeedbackDatabase:
    """Manages persistent feedback storage for ML pipeline optimization."""
    
    def __init__(self, db_path: str = "feedback_database.db"):
        self.db_path = Path(db_path)
        self._init_database()
    
    def _init_database(self):
        """Initialize the feedback database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Create feedback table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        drug_name TEXT NOT NULL,
                        query TEXT NOT NULL,
                        is_positive BOOLEAN NOT NULL,
                        user_id TEXT,
                        session_id TEXT,
                        timestamp REAL NOT NULL,
                        created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
                    )
                """)
                
                # Create indexes for faster queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_drug_query 
                    ON feedback(drug_name, query)
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_timestamp 
                    ON feedback(timestamp)
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_user 
                    ON feedback(user_id)
                """)
                
                conn.commit()
                logger.info(f"Feedback database initialized at {self.db_path}")
                
        except Exception as e:
            logger.error(f"Failed to initialize feedback database: {e}")
            raise
    
    def record_feedback(self, drug_name: str, query: str, is_positive: bool, 
                       user_id: Optional[str] = None, session_id: Optional[str] = None,
                       is_removal: bool = False) -> bool:
        """Record user feedback for a drug and query combination."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if is_removal:
                    # Remove the most recent feedback of the opposite type
                    opposite_type = not is_positive
                    cursor = conn.execute("""
                        DELETE FROM feedback 
                        WHERE drug_name = ? AND query = ? AND is_positive = ?
                        ORDER BY timestamp DESC 
                        LIMIT 1
                    """, (drug_name, query, opposite_type))
                    
                    if cursor.rowcount > 0:
                        logger.info(f"Removed feedback for {drug_name} with query {query}")
                        return True
                    else:
                        logger.warning(f"No feedback found to remove for {drug_name} with query {query}")
                        return False
                else:
                    # Add new feedback
                    conn.execute("""
                        INSERT INTO feedback (drug_name, query, is_positive, user_id, session_id, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (drug_name, query, is_positive, user_id, session_id, time.time()))
                    
                    conn.commit()
                    logger.info(f"Recorded feedback for {drug_name} with query {query}: {'positive' if is_positive else 'negative'}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return False
    
    def get_feedback_counts(self, drug_name: str, query: str) -> Dict[str, int]:
        """Get feedback counts for a specific drug and query combination."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        SUM(CASE WHEN is_positive = 1 THEN 1 ELSE 0 END) as helpful,
                        SUM(CASE WHEN is_positive = 0 THEN 1 ELSE 0 END) as not_helpful
                    FROM feedback 
                    WHERE drug_name = ? AND query = ?
                """, (drug_name, query))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "helpful": result[0] or 0,
                        "not_helpful": result[1] or 0
                    }
                else:
                    return {"helpful": 0, "not_helpful": 0}
                    
        except Exception as e:
            logger.error(f"Failed to get feedback counts: {e}")
            return {"helpful": 0, "not_helpful": 0}
    
    def get_all_feedback_counts(self) -> Dict[str, Dict[str, int]]:
        """Get all feedback counts grouped by drug_name+query."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        drug_name,
                        query,
                        SUM(CASE WHEN is_positive = 1 THEN 1 ELSE 0 END) as helpful,
                        SUM(CASE WHEN is_positive = 0 THEN 1 ELSE 0 END) as not_helpful
                    FROM feedback 
                    GROUP BY drug_name, query
                    ORDER BY helpful + not_helpful DESC
                """)
                
                feedback_counts = {}
                for row in cursor.fetchall():
                    key = f"{row[0]}_{row[1]}"
                    feedback_counts[key] = {
                        "drug_name": row[0],
                        "query": row[1],
                        "helpful": row[2] or 0,
                        "not_helpful": row[3] or 0
                    }
                
                return feedback_counts
                
        except Exception as e:
            logger.error(f"Failed to get all feedback counts: {e}")
            return {}
    
    def get_feedback_stats(self) -> Dict[str, any]:
        """Get overall feedback statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Total counts
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_feedback,
                        SUM(CASE WHEN is_positive = 1 THEN 1 ELSE 0 END) as total_helpful,
                        SUM(CASE WHEN is_positive = 0 THEN 1 ELSE 0 END) as total_not_helpful
                    FROM feedback
                """)
                
                stats = cursor.fetchone()
                
                # Recent feedback (last 24 hours)
                cursor = conn.execute("""
                    SELECT COUNT(*) as recent_feedback
                    FROM feedback 
                    WHERE timestamp > ?
                """, (time.time() - 86400,))
                
                recent_count = cursor.fetchone()[0] or 0
                
                return {
                    "total_feedback": stats[0] or 0,
                    "total_helpful": stats[1] or 0,
                    "total_not_helpful": stats[2] or 0,
                    "recent_feedback_24h": recent_count,
                    "helpful_percentage": (stats[1] / stats[0] * 100) if stats[0] > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"Failed to get feedback stats: {e}")
            return {
                "total_feedback": 0,
                "total_helpful": 0,
                "total_not_helpful": 0,
                "recent_feedback_24h": 0,
                "helpful_percentage": 0
            }
    
    def remove_feedback(self, drug_name: str, query: str) -> bool:
        """Remove all feedback for a specific drug and query combination."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM feedback 
                    WHERE drug_name = ? AND query = ?
                """, (drug_name, query))
                
                conn.commit()
                deleted_count = cursor.rowcount
                logger.info(f"Removed {deleted_count} feedback entries for {drug_name} with query {query}")
                return deleted_count > 0
                
        except Exception as e:
            logger.error(f"Failed to remove feedback: {e}")
            return False
    
    def clear_all_feedback(self) -> bool:
        """Clear all feedback data."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM feedback")
                conn.commit()
                deleted_count = cursor.rowcount
                logger.info(f"Cleared {deleted_count} feedback entries")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear all feedback: {e}")
            return False
    
    def get_ignored_medications(self, min_votes: int = 3, negative_threshold: float = 0.6) -> List[Dict[str, any]]:
        """Get medications that should be ignored based on feedback thresholds."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        drug_name,
                        query,
                        SUM(CASE WHEN is_positive = 1 THEN 1 ELSE 0 END) as helpful,
                        SUM(CASE WHEN is_positive = 0 THEN 1 ELSE 0 END) as not_helpful,
                        COUNT(*) as total_votes
                    FROM feedback 
                    GROUP BY drug_name, query
                    HAVING total_votes >= ? AND (not_helpful * 1.0 / total_votes) >= ?
                    ORDER BY (not_helpful * 1.0 / total_votes) DESC, total_votes DESC
                """, (min_votes, negative_threshold))
                
                ignored_medications = []
                for row in cursor.fetchall():
                    ignored_medications.append({
                        "drug_name": row[0],
                        "query": row[1],
                        "helpful_count": row[2] or 0,
                        "not_helpful_count": row[3] or 0,
                        "total_votes": row[4] or 0,
                        "negative_percentage": (row[3] / row[4] * 100) if row[4] > 0 else 0
                    })
                
                return ignored_medications
                
        except Exception as e:
            logger.error(f"Failed to get ignored medications: {e}")
            return []
    
    def is_medication_ignored(self, drug_name: str, query: str, min_votes: int = 3, negative_threshold: float = 0.6) -> bool:
        """Check if a specific medication should be ignored."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        SUM(CASE WHEN is_positive = 1 THEN 1 ELSE 0 END) as helpful,
                        SUM(CASE WHEN is_positive = 0 THEN 1 ELSE 0 END) as not_helpful,
                        COUNT(*) as total_votes
                    FROM feedback 
                    WHERE drug_name = ? AND query = ?
                """, (drug_name, query))
                
                result = cursor.fetchone()
                if result and result[2] >= min_votes:
                    negative_percentage = (result[1] / result[2]) if result[2] > 0 else 0
                    return negative_percentage >= negative_threshold
                
                return False
                
        except Exception as e:
            logger.error(f"Failed to check if medication is ignored: {e}")
            return False
    
    def get_database_stats(self) -> Dict[str, any]:
        """Get database statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM feedback")
                total_records = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(DISTINCT drug_name) FROM feedback")
                unique_drugs = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(DISTINCT query) FROM feedback")
                unique_queries = cursor.fetchone()[0]
                
                # Get ignored medications count
                ignored_count = len(self.get_ignored_medications())
                
                return {
                    "total_records": total_records,
                    "unique_drugs": unique_drugs,
                    "unique_queries": unique_queries,
                    "ignored_medications": ignored_count,
                    "database_size_mb": self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {
                "total_records": 0,
                "unique_drugs": 0,
                "unique_queries": 0,
                "ignored_medications": 0,
                "database_size_mb": 0
            }
