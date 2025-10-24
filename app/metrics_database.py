"""
Metrics Database Module
Tracks comprehensive system metrics for admin dashboard
"""

import sqlite3
import json
import time
from typing import Dict, List, Optional, Tuple, Any
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MetricsDatabase:
    """Manages persistent storage of system metrics."""
    
    def __init__(self, db_path: str = "metrics_database.db"):
        self.db_path = db_path
        self._initialize_database()
        logger.info(f"Metrics database initialized at {db_path}")
    
    def _initialize_database(self):
        """Initialize the metrics database with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Search metrics table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS search_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query TEXT NOT NULL,
                        results_count INTEGER DEFAULT 0,
                        response_time_ms REAL DEFAULT 0,
                        timestamp REAL NOT NULL,
                        user_id TEXT,
                        session_id TEXT,
                        api_calls_count INTEGER DEFAULT 0,
                        cache_hits INTEGER DEFAULT 0,
                        cache_misses INTEGER DEFAULT 0
                    )
                """)
                
                # API call metrics table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS api_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        api_name TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        response_time_ms REAL DEFAULT 0,
                        status_code INTEGER DEFAULT 200,
                        success BOOLEAN DEFAULT 1,
                        timestamp REAL NOT NULL,
                        search_query TEXT,
                        results_count INTEGER DEFAULT 0
                    )
                """)
                
                # System performance metrics table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        timestamp REAL NOT NULL,
                        metadata TEXT
                    )
                """)
                
                # User activity metrics table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_activity (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        session_id TEXT,
                        action TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        metadata TEXT
                    )
                """)
                
                # Create indexes for better performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_search_metrics_timestamp ON search_metrics(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_api_metrics_timestamp ON api_metrics(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON system_metrics(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_timestamp ON user_activity(timestamp)")
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to initialize metrics database: {e}")
            raise
    
    def record_search_metric(self, query: str, results_count: int, response_time_ms: float, 
                           user_id: str = None, session_id: str = None, 
                           api_calls_count: int = 0, cache_hits: int = 0, cache_misses: int = 0):
        """Record a search metric."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO search_metrics 
                    (query, results_count, response_time_ms, timestamp, user_id, session_id, 
                     api_calls_count, cache_hits, cache_misses)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (query, results_count, response_time_ms, time.time(), user_id, session_id,
                      api_calls_count, cache_hits, cache_misses))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record search metric: {e}")
    
    def record_api_metric(self, api_name: str, endpoint: str, response_time_ms: float,
                         status_code: int = 200, success: bool = True, 
                         search_query: str = None, results_count: int = 0):
        """Record an API call metric."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO api_metrics 
                    (api_name, endpoint, response_time_ms, status_code, success, 
                     timestamp, search_query, results_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (api_name, endpoint, response_time_ms, status_code, success,
                      time.time(), search_query, results_count))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record API metric: {e}")
    
    def record_system_metric(self, metric_name: str, metric_value: float, metadata: str = None):
        """Record a system performance metric."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO system_metrics (metric_name, metric_value, timestamp, metadata)
                    VALUES (?, ?, ?, ?)
                """, (metric_name, metric_value, time.time(), metadata))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record system metric: {e}")
    
    def record_user_activity(self, action: str, user_id: str = None, session_id: str = None, metadata: str = None):
        """Record user activity."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO user_activity (user_id, session_id, action, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, session_id, action, time.time(), metadata))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record user activity: {e}")
    
    def get_metrics_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive metrics summary for the specified time period."""
        try:
            cutoff_time = time.time() - (time_period_hours * 3600)
            
            with sqlite3.connect(self.db_path) as conn:
                # Search metrics
                search_cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        AVG(response_time_ms) as avg_response_time,
                        SUM(results_count) as total_results,
                        AVG(results_count) as avg_results_per_search,
                        COUNT(DISTINCT query) as unique_queries,
                        SUM(api_calls_count) as total_api_calls,
                        SUM(cache_hits) as total_cache_hits,
                        SUM(cache_misses) as total_cache_misses
                    FROM search_metrics 
                    WHERE timestamp >= ?
                """, (cutoff_time,))
                
                search_stats = search_cursor.fetchone()
                
                # API metrics
                api_cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_api_calls,
                        AVG(response_time_ms) as avg_api_response_time,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_calls,
                        COUNT(DISTINCT api_name) as unique_apis
                    FROM api_metrics 
                    WHERE timestamp >= ?
                """, (cutoff_time,))
                
                api_stats = api_cursor.fetchone()
                
                # User activity
                activity_cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_activities,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(DISTINCT session_id) as unique_sessions
                    FROM user_activity 
                    WHERE timestamp >= ?
                """, (cutoff_time,))
                
                activity_stats = activity_cursor.fetchone()
                
                # Top queries
                top_queries_cursor = conn.execute("""
                    SELECT query, COUNT(*) as search_count
                    FROM search_metrics 
                    WHERE timestamp >= ?
                    GROUP BY query
                    ORDER BY search_count DESC
                    LIMIT 10
                """, (cutoff_time,))
                
                top_queries = [{"query": row[0], "count": row[1]} for row in top_queries_cursor.fetchall()]
                
                # API performance by service
                api_performance_cursor = conn.execute("""
                    SELECT 
                        api_name,
                        COUNT(*) as call_count,
                        AVG(response_time_ms) as avg_response_time,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls
                    FROM api_metrics 
                    WHERE timestamp >= ?
                    GROUP BY api_name
                    ORDER BY call_count DESC
                """, (cutoff_time,))
                
                api_performance = []
                for row in api_performance_cursor.fetchall():
                    api_performance.append({
                        "api_name": row[0],
                        "call_count": row[1],
                        "avg_response_time": round(row[2] or 0, 2),
                        "success_rate": round((row[3] / row[1]) * 100, 2) if row[1] > 0 else 0
                    })
                
                return {
                    "time_period_hours": time_period_hours,
                    "search_metrics": {
                        "total_searches": search_stats[0] or 0,
                        "avg_response_time_ms": round(search_stats[1] or 0, 2),
                        "total_results": search_stats[2] or 0,
                        "avg_results_per_search": round(search_stats[3] or 0, 2),
                        "unique_queries": search_stats[4] or 0,
                        "total_api_calls": search_stats[5] or 0,
                        "cache_hit_rate": round((search_stats[6] / (search_stats[6] + search_stats[7])) * 100, 2) if (search_stats[6] or 0) + (search_stats[7] or 0) > 0 else 0
                    },
                    "api_metrics": {
                        "total_api_calls": api_stats[0] or 0,
                        "avg_response_time_ms": round(api_stats[1] or 0, 2),
                        "success_rate": round((api_stats[2] / api_stats[0]) * 100, 2) if api_stats[0] > 0 else 0,
                        "failed_calls": api_stats[3] or 0,
                        "unique_apis": api_stats[4] or 0
                    },
                    "user_activity": {
                        "total_activities": activity_stats[0] or 0,
                        "unique_users": activity_stats[1] or 0,
                        "unique_sessions": activity_stats[2] or 0
                    },
                    "top_queries": top_queries,
                    "api_performance": api_performance,
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {
                "time_period_hours": time_period_hours,
                "error": str(e),
                "timestamp": time.time()
            }
    
    def get_time_series_data(self, metric_type: str, time_period_hours: int = 24, 
                           interval_hours: int = 1) -> List[Dict[str, Any]]:
        """Get time series data for charts."""
        try:
            cutoff_time = time.time() - (time_period_hours * 3600)
            interval_seconds = interval_hours * 3600
            
            if metric_type == "searches":
                table = "search_metrics"
                group_by = "timestamp"
                select_fields = "COUNT(*) as count, AVG(response_time_ms) as avg_response_time"
            elif metric_type == "api_calls":
                table = "api_metrics"
                group_by = "timestamp"
                select_fields = "COUNT(*) as count, AVG(response_time_ms) as avg_response_time"
            else:
                return []
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(f"""
                    SELECT 
                        FLOOR(timestamp / ?) * ? as time_bucket,
                        {select_fields}
                    FROM {table}
                    WHERE timestamp >= ?
                    GROUP BY time_bucket
                    ORDER BY time_bucket
                """, (interval_seconds, interval_seconds, cutoff_time))
                
                time_series = []
                for row in cursor.fetchall():
                    time_series.append({
                        "timestamp": row[0],
                        "count": row[1],
                        "avg_response_time": round(row[2] or 0, 2)
                    })
                
                return time_series
                
        except Exception as e:
            logger.error(f"Failed to get time series data: {e}")
            return []
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old metrics data to prevent database bloat."""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            
            with sqlite3.connect(self.db_path) as conn:
                # Delete old records from all tables
                tables = ["search_metrics", "api_metrics", "system_metrics", "user_activity"]
                deleted_count = 0
                
                for table in tables:
                    cursor = conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff_time,))
                    deleted_count += cursor.rowcount
                
                conn.commit()
                logger.info(f"Cleaned up {deleted_count} old metric records")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
