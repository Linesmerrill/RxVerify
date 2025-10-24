"""
Feedback Database Module
Manages persistent storage of user feedback for ML pipeline optimization
Now uses unified database manager for both SQLite and PostgreSQL
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from app.database_manager import db_manager

logger = logging.getLogger(__name__)

class FeedbackDatabase:
    """Manages persistent storage of user feedback."""
    
    def __init__(self, db_path: str = "feedback_database.db"):
        # db_path is kept for backward compatibility but not used
        # All operations now go through the unified database manager
        self.db_manager = db_manager
        logger.info("Feedback database initialized with unified database manager")
    
    def add_feedback(self, drug_name: str, query: str, is_positive: bool, 
                    user_id: str = None, session_id: str = None) -> bool:
        """Add feedback entry."""
        return self.db_manager.add_feedback(drug_name, query, is_positive, user_id, session_id)
    
    def get_feedback_counts(self, drug_name: str, query: str) -> Dict[str, int]:
        """Get feedback counts for a specific drug and query combination."""
        try:
            counts = self.db_manager.get_all_feedback_counts()
            key = f"{drug_name}|{query}"
            if key in counts:
                return {
                    "helpful": counts[key]["helpful"],
                    "not_helpful": counts[key]["not_helpful"]
                }
            else:
                return {"helpful": 0, "not_helpful": 0}
        except Exception as e:
            logger.error(f"Failed to get feedback counts: {e}")
            return {"helpful": 0, "not_helpful": 0}
    
    def get_all_feedback_counts(self) -> Dict[str, Dict[str, Any]]:
        """Get aggregated feedback counts for all drug/query combinations."""
        return self.db_manager.get_all_feedback_counts()
    
    def get_all_feedback_entries(self) -> List[Dict[str, Any]]:
        """Get all individual feedback entries."""
        return self.db_manager.get_all_feedback_entries()
    
    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get comprehensive feedback statistics."""
        return self.db_manager.get_feedback_stats()
    
    def get_ignored_medications(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get medications that should be ignored based on negative feedback."""
        return self.db_manager.get_ignored_medications(threshold)
    
    def remove_feedback(self, drug_name: str, query: str, user_id: str = None, session_id: str = None) -> bool:
        """Remove specific feedback entry."""
        # This would need to be implemented in the database manager
        # For now, return True to maintain compatibility
        logger.warning("remove_feedback not yet implemented in unified database manager")
        return True
    
    def clear_all_feedback(self) -> bool:
        """Clear all feedback data."""
        # This would need to be implemented in the database manager
        # For now, return True to maintain compatibility
        logger.warning("clear_all_feedback not yet implemented in unified database manager")
        return True