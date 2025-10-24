"""
Database Manager
Unified interface for database operations across SQLite and PostgreSQL
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, or_

from app.database_config import db_config
from app.database_models import (
    FeedbackEntry, SearchMetric, ApiMetric, SystemMetric, 
    UserActivity, MedicationCache, RxListDrug
)

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Unified database manager for all operations."""
    
    def __init__(self):
        self.db_config = db_config
        self.SessionLocal = self.db_config.get_session_local()
        
    def get_session(self) -> Session:
        """Get database session."""
        return self.SessionLocal()
    
    def create_tables(self):
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.db_config.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    # Feedback Operations
    def add_feedback(self, drug_name: str, query: str, is_positive: bool, 
                    user_id: str = None, session_id: str = None) -> bool:
        """Add feedback entry."""
        try:
            with self.get_session() as db:
                feedback = FeedbackEntry(
                    drug_name=drug_name,
                    query=query,
                    is_positive=is_positive,
                    user_id=user_id,
                    session_id=session_id
                )
                db.add(feedback)
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to add feedback: {e}")
            return False
    
    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get feedback statistics."""
        try:
            with self.get_session() as db:
                # Total feedback
                total_feedback = db.query(func.count(FeedbackEntry.id)).scalar() or 0
                
                # Positive/negative counts
                positive_count = db.query(func.count(FeedbackEntry.id)).filter(
                    FeedbackEntry.is_positive == True
                ).scalar() or 0
                
                negative_count = db.query(func.count(FeedbackEntry.id)).filter(
                    FeedbackEntry.is_positive == False
                ).scalar() or 0
                
                # Recent feedback (24h)
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                recent_feedback = db.query(func.count(FeedbackEntry.id)).filter(
                    FeedbackEntry.timestamp >= cutoff_time
                ).scalar() or 0
                
                # Helpful percentage
                helpful_percentage = (positive_count / total_feedback * 100) if total_feedback > 0 else 0
                
                return {
                    "total_feedback": total_feedback,
                    "total_helpful": positive_count,
                    "total_not_helpful": negative_count,
                    "recent_feedback_24h": recent_feedback,
                    "helpful_percentage": helpful_percentage
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
    
    def get_all_feedback_entries(self) -> List[Dict[str, Any]]:
        """Get all feedback entries."""
        try:
            with self.get_session() as db:
                entries = db.query(FeedbackEntry).order_by(FeedbackEntry.timestamp.desc()).all()
                return [
                    {
                        "drug_name": entry.drug_name,
                        "query": entry.query,
                        "is_positive": entry.is_positive,
                        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                        "user_id": entry.user_id,
                        "session_id": entry.session_id
                    }
                    for entry in entries
                ]
        except Exception as e:
            logger.error(f"Failed to get feedback entries: {e}")
            return []
    
    def get_all_feedback_counts(self) -> Dict[str, Dict[str, Any]]:
        """Get aggregated feedback counts."""
        try:
            with self.get_session() as db:
                # Group by drug_name and query, count positive/negative
                results = db.query(
                    FeedbackEntry.drug_name,
                    FeedbackEntry.query,
                    func.sum(func.case([(FeedbackEntry.is_positive == True, 1)], else_=0)).label('helpful'),
                    func.sum(func.case([(FeedbackEntry.is_positive == False, 1)], else_=0)).label('not_helpful')
                ).group_by(FeedbackEntry.drug_name, FeedbackEntry.query).all()
                
                feedback_counts = {}
                for row in results:
                    key = f"{row.drug_name}|{row.query}"
                    feedback_counts[key] = {
                        "drug_name": row.drug_name,
                        "query": row.query,
                        "helpful": row.helpful or 0,
                        "not_helpful": row.not_helpful or 0
                    }
                
                return feedback_counts
        except Exception as e:
            logger.error(f"Failed to get feedback counts: {e}")
            return {}
    
    def get_ignored_medications(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get medications that should be ignored based on negative feedback."""
        try:
            with self.get_session() as db:
                # Find medications with high negative feedback ratio
                results = db.query(
                    FeedbackEntry.drug_name,
                    FeedbackEntry.query,
                    func.count(FeedbackEntry.id).label('total_votes'),
                    func.sum(func.case([(FeedbackEntry.is_positive == False, 1)], else_=0)).label('negative_votes')
                ).group_by(FeedbackEntry.drug_name, FeedbackEntry.query).having(
                    func.count(FeedbackEntry.id) >= 3  # Minimum votes
                ).all()
                
                ignored = []
                for row in results:
                    negative_ratio = (row.negative_votes or 0) / row.total_votes
                    if negative_ratio >= threshold:
                        ignored.append({
                            "drug_name": row.drug_name,
                            "query": row.query,
                            "negative_percentage": round(negative_ratio * 100, 2),
                            "total_votes": row.total_votes
                        })
                
                return ignored
        except Exception as e:
            logger.error(f"Failed to get ignored medications: {e}")
            return []
    
    # Search Metrics Operations
    def record_search_metric(self, query: str, results_count: int, response_time_ms: float,
                           user_id: str = None, session_id: str = None,
                           api_calls_count: int = 0, cache_hits: int = 0, cache_misses: int = 0):
        """Record search metric."""
        try:
            with self.get_session() as db:
                metric = SearchMetric(
                    query=query,
                    results_count=results_count,
                    response_time_ms=response_time_ms,
                    user_id=user_id,
                    session_id=session_id,
                    api_calls_count=api_calls_count,
                    cache_hits=cache_hits,
                    cache_misses=cache_misses
                )
                db.add(metric)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to record search metric: {e}")
    
    def record_api_metric(self, api_name: str, endpoint: str, response_time_ms: float,
                         status_code: int = 200, success: bool = True,
                         search_query: str = None, results_count: int = 0):
        """Record API metric."""
        try:
            with self.get_session() as db:
                metric = ApiMetric(
                    api_name=api_name,
                    endpoint=endpoint,
                    response_time_ms=response_time_ms,
                    status_code=status_code,
                    success=success,
                    search_query=search_query,
                    results_count=results_count
                )
                db.add(metric)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to record API metric: {e}")
    
    def record_user_activity(self, action: str, user_id: str = None, 
                           session_id: str = None, metadata: str = None):
        """Record user activity."""
        try:
            with self.get_session() as db:
                activity = UserActivity(
                    action=action,
                    user_id=user_id,
                    session_id=session_id,
                    metadata=metadata
                )
                db.add(activity)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to record user activity: {e}")
    
    def get_metrics_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            
            with self.get_session() as db:
                # Search metrics
                search_stats = db.query(
                    func.count(SearchMetric.id).label('total_searches'),
                    func.avg(SearchMetric.response_time_ms).label('avg_response_time'),
                    func.sum(SearchMetric.results_count).label('total_results'),
                    func.avg(SearchMetric.results_count).label('avg_results_per_search'),
                    func.count(func.distinct(SearchMetric.query)).label('unique_queries'),
                    func.sum(SearchMetric.api_calls_count).label('total_api_calls'),
                    func.sum(SearchMetric.cache_hits).label('total_cache_hits'),
                    func.sum(SearchMetric.cache_misses).label('total_cache_misses')
                ).filter(SearchMetric.timestamp >= cutoff_time).first()
                
                # API metrics
                api_stats = db.query(
                    func.count(ApiMetric.id).label('total_api_calls'),
                    func.avg(ApiMetric.response_time_ms).label('avg_api_response_time'),
                    func.sum(func.case([(ApiMetric.success == True, 1)], else_=0)).label('successful_calls'),
                    func.sum(func.case([(ApiMetric.success == False, 1)], else_=0)).label('failed_calls'),
                    func.count(func.distinct(ApiMetric.api_name)).label('unique_apis')
                ).filter(ApiMetric.timestamp >= cutoff_time).first()
                
                # User activity
                activity_stats = db.query(
                    func.count(UserActivity.id).label('total_activities'),
                    func.count(func.distinct(UserActivity.user_id)).label('unique_users'),
                    func.count(func.distinct(UserActivity.session_id)).label('unique_sessions')
                ).filter(UserActivity.timestamp >= cutoff_time).first()
                
                # Top queries
                top_queries = db.query(
                    SearchMetric.query,
                    func.count(SearchMetric.id).label('search_count')
                ).filter(SearchMetric.timestamp >= cutoff_time).group_by(
                    SearchMetric.query
                ).order_by(func.count(SearchMetric.id).desc()).limit(10).all()
                
                # API performance by service
                api_performance = db.query(
                    ApiMetric.api_name,
                    func.count(ApiMetric.id).label('call_count'),
                    func.avg(ApiMetric.response_time_ms).label('avg_response_time'),
                    func.sum(func.case([(ApiMetric.success == True, 1)], else_=0)).label('successful_calls')
                ).filter(ApiMetric.timestamp >= cutoff_time).group_by(
                    ApiMetric.api_name
                ).order_by(func.count(ApiMetric.id).desc()).all()
                
                return {
                    "time_period_hours": time_period_hours,
                    "search_metrics": {
                        "total_searches": search_stats.total_searches or 0,
                        "avg_response_time_ms": round(search_stats.avg_response_time or 0, 2),
                        "total_results": search_stats.total_results or 0,
                        "avg_results_per_search": round(search_stats.avg_results_per_search or 0, 2),
                        "unique_queries": search_stats.unique_queries or 0,
                        "total_api_calls": search_stats.total_api_calls or 0,
                        "cache_hit_rate": round(
                            (search_stats.total_cache_hits or 0) / 
                            ((search_stats.total_cache_hits or 0) + (search_stats.total_cache_misses or 0)) * 100, 2
                        ) if (search_stats.total_cache_hits or 0) + (search_stats.total_cache_misses or 0) > 0 else 0
                    },
                    "api_metrics": {
                        "total_api_calls": api_stats.total_api_calls or 0,
                        "avg_response_time_ms": round(api_stats.avg_api_response_time or 0, 2),
                        "success_rate": round((api_stats.successful_calls or 0) / (api_stats.total_api_calls or 1) * 100, 2),
                        "failed_calls": api_stats.failed_calls or 0,
                        "unique_apis": api_stats.unique_apis or 0
                    },
                    "user_activity": {
                        "total_activities": activity_stats.total_activities or 0,
                        "unique_users": activity_stats.unique_users or 0,
                        "unique_sessions": activity_stats.unique_sessions or 0
                    },
                    "top_queries": [{"query": row.query, "count": row.search_count} for row in top_queries],
                    "api_performance": [
                        {
                            "api_name": row.api_name,
                            "call_count": row.call_count,
                            "avg_response_time": round(row.avg_response_time or 0, 2),
                            "success_rate": round((row.successful_calls / row.call_count) * 100, 2) if row.call_count > 0 else 0
                        }
                        for row in api_performance
                    ],
                    "timestamp": datetime.utcnow().timestamp()
                }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {
                "time_period_hours": time_period_hours,
                "error": str(e),
                "timestamp": datetime.utcnow().timestamp()
            }
    
    def get_time_series_data(self, metric_type: str, time_period_hours: int = 24, 
                           interval_hours: int = 1) -> List[Dict[str, Any]]:
        """Get time series data for charts."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            interval_seconds = interval_hours * 3600
            
            with self.get_session() as db:
                if metric_type == "searches":
                    # Use PostgreSQL's date_trunc for time bucketing
                    if self.db_config.is_postgres:
                        results = db.execute(text("""
                            SELECT 
                                EXTRACT(EPOCH FROM date_trunc('hour', timestamp)) as time_bucket,
                                COUNT(*) as count,
                                AVG(response_time_ms) as avg_response_time
                            FROM search_metrics 
                            WHERE timestamp >= :cutoff_time
                            GROUP BY date_trunc('hour', timestamp)
                            ORDER BY time_bucket
                        """), {"cutoff_time": cutoff_time}).fetchall()
                    else:
                        # SQLite fallback
                        results = db.execute(text("""
                            SELECT 
                                CAST(timestamp / :interval_seconds AS INTEGER) * :interval_seconds as time_bucket,
                                COUNT(*) as count,
                                AVG(response_time_ms) as avg_response_time
                            FROM search_metrics 
                            WHERE timestamp >= :cutoff_time
                            GROUP BY time_bucket
                            ORDER BY time_bucket
                        """), {
                            "cutoff_time": cutoff_time,
                            "interval_seconds": interval_seconds
                        }).fetchall()
                
                elif metric_type == "api_calls":
                    if self.db_config.is_postgres:
                        results = db.execute(text("""
                            SELECT 
                                EXTRACT(EPOCH FROM date_trunc('hour', timestamp)) as time_bucket,
                                COUNT(*) as count,
                                AVG(response_time_ms) as avg_response_time
                            FROM api_metrics 
                            WHERE timestamp >= :cutoff_time
                            GROUP BY date_trunc('hour', timestamp)
                            ORDER BY time_bucket
                        """), {"cutoff_time": cutoff_time}).fetchall()
                    else:
                        results = db.execute(text("""
                            SELECT 
                                CAST(timestamp / :interval_seconds AS INTEGER) * :interval_seconds as time_bucket,
                                COUNT(*) as count,
                                AVG(response_time_ms) as avg_response_time
                            FROM api_metrics 
                            WHERE timestamp >= :cutoff_time
                            GROUP BY time_bucket
                            ORDER BY time_bucket
                        """), {
                            "cutoff_time": cutoff_time,
                            "interval_seconds": interval_seconds
                        }).fetchall()
                else:
                    return []
                
                return [
                    {
                        "timestamp": row.time_bucket,
                        "count": row.count,
                        "avg_response_time": round(row.avg_response_time or 0, 2)
                    }
                    for row in results
                ]
        except Exception as e:
            logger.error(f"Failed to get time series data: {e}")
            return []
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old data to prevent database bloat."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=days_to_keep)
            
            with self.get_session() as db:
                # Delete old records from all tables
                tables = [FeedbackEntry, SearchMetric, ApiMetric, SystemMetric, UserActivity]
                deleted_count = 0
                
                for table in tables:
                    result = db.query(table).filter(table.timestamp < cutoff_time).delete()
                    deleted_count += result
                
                db.commit()
                logger.info(f"Cleaned up {deleted_count} old records")
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")

# Global database manager instance
db_manager = DatabaseManager()
