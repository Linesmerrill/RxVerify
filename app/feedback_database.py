"""
Feedback Database Module
Manages persistent storage of user feedback for ML pipeline optimization
Now supports both SQLite/PostgreSQL and MongoDB
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
import os

logger = logging.getLogger(__name__)

class FeedbackDatabase:
    """Manages persistent storage of user feedback."""
    
    def __init__(self, db_path: str = "feedback_database.db"):
        # Determine which database to use based on environment
        self.use_mongodb = self._should_use_mongodb()
        
        if self.use_mongodb:
            from app.mongodb_manager import mongodb_manager
            self.db_manager = mongodb_manager
            logger.info("Feedback database initialized with MongoDB")
        else:
            from app.database_manager import db_manager
            self.db_manager = db_manager
            logger.info("Feedback database initialized with SQL/PostgreSQL")
    
    def _should_use_mongodb(self) -> bool:
        """Determine if MongoDB should be used based on environment variables."""
        return 'MONGODB_URI' in os.environ or 'MONGODB_URL' in os.environ
    
    async def add_feedback(self, drug_name: str, query: str, is_positive: bool, 
                          user_id: str = None, session_id: str = None) -> bool:
        """Add feedback entry."""
        if self.use_mongodb:
            return await self.db_manager.add_feedback(drug_name, query, is_positive, user_id, session_id)
        else:
            return self.db_manager.add_feedback(drug_name, query, is_positive, user_id, session_id)
    
    async def get_feedback_counts(self, drug_name: str, query: str) -> Dict[str, int]:
        """Get feedback counts for a specific drug and query combination."""
        try:
            if self.use_mongodb:
                counts = await self.db_manager.get_all_feedback_counts()
            else:
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
    
    async def get_all_feedback_counts(self) -> Dict[str, Dict[str, Any]]:
        """Get aggregated feedback counts for all drug/query combinations."""
        if self.use_mongodb:
            return await self.db_manager.get_all_feedback_counts()
        else:
            return self.db_manager.get_all_feedback_counts()
    
    async def get_all_feedback_entries(self) -> List[Dict[str, Any]]:
        """Get all individual feedback entries."""
        if self.use_mongodb:
            return await self.db_manager.get_all_feedback_entries()
        else:
            return self.db_manager.get_all_feedback_entries()
    
    async def get_feedback_stats(self) -> Dict[str, Any]:
        """Get comprehensive feedback statistics."""
        if self.use_mongodb:
            return await self.db_manager.get_feedback_stats()
        else:
            return self.db_manager.get_feedback_stats()
    
    async def get_ignored_medications(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get medications that should be ignored based on negative feedback."""
        if self.use_mongodb:
            return await self.db_manager.get_ignored_medications(threshold)
        else:
            return self.db_manager.get_ignored_medications(threshold)
    
    def remove_feedback(self, drug_name: str, query: str, user_id: str = None, session_id: str = None) -> bool:
        """Remove specific feedback entry."""
        # This would need to be implemented in both database managers
        logger.warning("remove_feedback not yet implemented in database managers")
        return True
    
    def clear_all_feedback(self) -> bool:
        """Clear all feedback data."""
        # This would need to be implemented in both database managers
        logger.warning("clear_all_feedback not yet implemented in database managers")
        return True
    
    async def is_medication_ignored(self, drug_name: str, query: str) -> bool:
        """Check if a medication should be ignored based on feedback."""
        try:
            ignored_meds = await self.get_ignored_medications()
            for med in ignored_meds:
                if med.get('drug_name') == drug_name:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking if medication is ignored: {e}")
            return False