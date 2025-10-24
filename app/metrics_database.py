"""
Metrics Database Module
Tracks comprehensive system metrics for admin dashboard
Now supports both SQLite/PostgreSQL and MongoDB
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
import os

logger = logging.getLogger(__name__)

class MetricsDatabase:
    """Manages persistent storage of system metrics."""
    
    def __init__(self, db_path: str = "metrics_database.db"):
        # Determine which database to use based on environment
        self.use_mongodb = self._should_use_mongodb()
        
        if self.use_mongodb:
            from app.mongodb_manager import mongodb_manager
            self.db_manager = mongodb_manager
            logger.info("Metrics database initialized with MongoDB")
        else:
            from app.database_manager import db_manager
            self.db_manager = db_manager
            logger.info("Metrics database initialized with SQL/PostgreSQL")
    
    def _should_use_mongodb(self) -> bool:
        """Determine if MongoDB should be used based on environment variables."""
        return 'MONGODB_URI' in os.environ or 'MONGODB_URL' in os.environ
    
    async def record_search_metric(self, query: str, results_count: int, response_time_ms: float, 
                                  user_id: str = None, session_id: str = None, 
                                  api_calls_count: int = 0, cache_hits: int = 0, cache_misses: int = 0):
        """Record a search metric."""
        if self.use_mongodb:
            await self.db_manager.record_search_metric(
                query, results_count, response_time_ms, user_id, session_id,
                api_calls_count, cache_hits, cache_misses
            )
        else:
            self.db_manager.record_search_metric(
                query, results_count, response_time_ms, user_id, session_id,
                api_calls_count, cache_hits, cache_misses
            )
    
    async def record_api_metric(self, api_name: str, endpoint: str, response_time_ms: float,
                               status_code: int = 200, success: bool = True, 
                               search_query: str = None, results_count: int = 0):
        """Record an API call metric."""
        if self.use_mongodb:
            await self.db_manager.record_api_metric(
                api_name, endpoint, response_time_ms, status_code, success,
                search_query, results_count
            )
        else:
            self.db_manager.record_api_metric(
                api_name, endpoint, response_time_ms, status_code, success,
                search_query, results_count
            )
    
    async def record_system_metric(self, metric_name: str, metric_value: float, metadata: str = None):
        """Record a system performance metric."""
        # This would need to be implemented in both database managers
        logger.warning("record_system_metric not yet implemented in database managers")
    
    async def record_user_activity(self, action: str, user_id: str = None, session_id: str = None, metadata: str = None):
        """Record user activity."""
        if self.use_mongodb:
            await self.db_manager.record_user_activity(action, user_id, session_id, metadata)
        else:
            self.db_manager.record_user_activity(action, user_id, session_id, metadata)
    
    async def get_metrics_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive metrics summary for the specified time period."""
        if self.use_mongodb:
            return await self.db_manager.get_metrics_summary(time_period_hours)
        else:
            return self.db_manager.get_metrics_summary(time_period_hours)
    
    async def get_time_series_data(self, metric_type: str, time_period_hours: int = 24, 
                                  interval_hours: int = 1) -> List[Dict[str, Any]]:
        """Get time series data for charts."""
        if self.use_mongodb:
            return await self.db_manager.get_time_series_data(metric_type, time_period_hours, interval_hours)
        else:
            return self.db_manager.get_time_series_data(metric_type, time_period_hours, interval_hours)
    
    async def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old metrics data to prevent database bloat."""
        if self.use_mongodb:
            await self.db_manager.cleanup_old_data(days_to_keep)
        else:
            self.db_manager.cleanup_old_data(days_to_keep)