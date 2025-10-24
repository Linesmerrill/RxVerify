"""
MongoDB Database Manager
Unified interface for MongoDB operations
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from app.mongodb_config import mongodb_config
from app.mongodb_models import (
    FeedbackDocument, SearchMetricDocument, ApiMetricDocument,
    SystemMetricDocument, UserActivityDocument, MedicationCacheDocument,
    RxListDrugDocument
)

logger = logging.getLogger(__name__)

class MongoDBManager:
    """Unified MongoDB manager for all operations."""
    
    def __init__(self):
        self.mongodb_config = mongodb_config
        self.database: Optional[AsyncIOMotorDatabase] = None
        
    async def get_database(self) -> AsyncIOMotorDatabase:
        """Get MongoDB database instance."""
        if not self.database:
            self.database = await self.mongodb_config.connect()
        return self.database
    
    async def create_indexes(self):
        """Create database indexes for better performance."""
        try:
            db = await self.get_database()
            
            # Feedback collection indexes
            await db.feedback.create_index([("drug_name", ASCENDING), ("query", ASCENDING)])
            await db.feedback.create_index([("timestamp", DESCENDING)])
            await db.feedback.create_index([("user_id", ASCENDING)])
            
            # Search metrics indexes
            await db.search_metrics.create_index([("query", ASCENDING), ("timestamp", DESCENDING)])
            await db.search_metrics.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
            
            # API metrics indexes
            await db.api_metrics.create_index([("api_name", ASCENDING), ("timestamp", DESCENDING)])
            await db.api_metrics.create_index([("success", ASCENDING), ("timestamp", DESCENDING)])
            
            # User activity indexes
            await db.user_activity.create_index([("user_id", ASCENDING), ("action", ASCENDING)])
            await db.user_activity.create_index([("session_id", ASCENDING), ("timestamp", DESCENDING)])
            
            # Medication cache indexes
            await db.medication_cache.create_index([("query", ASCENDING)], unique=True)
            
            # RxList drugs indexes
            await db.rxlist_drugs.create_index([("name", ASCENDING)])
            await db.rxlist_drugs.create_index([("generic_name", ASCENDING)])
            await db.rxlist_drugs.create_index([("drug_class", ASCENDING)])
            
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.error(f"Failed to create MongoDB indexes: {e}")
            raise
    
    # Feedback Operations
    async def add_feedback(self, drug_name: str, query: str, is_positive: bool, 
                          user_id: str = None, session_id: str = None) -> bool:
        """Add feedback entry."""
        try:
            db = await self.get_database()
            feedback = FeedbackDocument(
                drug_name=drug_name,
                query=query,
                is_positive=is_positive,
                user_id=user_id,
                session_id=session_id
            )
            await db.feedback.insert_one(feedback.dict(by_alias=True))
            return True
        except Exception as e:
            logger.error(f"Failed to add feedback: {e}")
            return False
    
    async def get_feedback_stats(self) -> Dict[str, Any]:
        """Get feedback statistics."""
        try:
            db = await self.get_database()
            
            # Total feedback
            total_feedback = await db.feedback.count_documents({})
            
            # Positive/negative counts
            positive_count = await db.feedback.count_documents({"is_positive": True})
            negative_count = await db.feedback.count_documents({"is_positive": False})
            
            # Recent feedback (24h)
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            recent_feedback = await db.feedback.count_documents({
                "timestamp": {"$gte": cutoff_time}
            })
            
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
    
    async def get_all_feedback_entries(self) -> List[Dict[str, Any]]:
        """Get all feedback entries."""
        try:
            db = await self.get_database()
            cursor = db.feedback.find().sort("timestamp", DESCENDING)
            entries = []
            async for doc in cursor:
                entries.append({
                    "drug_name": doc["drug_name"],
                    "query": doc["query"],
                    "is_positive": doc["is_positive"],
                    "timestamp": doc["timestamp"].isoformat(),
                    "user_id": doc.get("user_id"),
                    "session_id": doc.get("session_id")
                })
            return entries
        except Exception as e:
            logger.error(f"Failed to get feedback entries: {e}")
            return []
    
    async def get_all_feedback_counts(self) -> Dict[str, Dict[str, Any]]:
        """Get aggregated feedback counts."""
        try:
            db = await self.get_database()
            
            # Aggregate feedback by drug_name and query
            pipeline = [
                {
                    "$group": {
                        "_id": {"drug_name": "$drug_name", "query": "$query"},
                        "helpful": {"$sum": {"$cond": [{"$eq": ["$is_positive", True]}, 1, 0]}},
                        "not_helpful": {"$sum": {"$cond": [{"$eq": ["$is_positive", False]}, 1, 0]}}
                    }
                },
                {
                    "$sort": {"helpful": -1, "not_helpful": -1}
                }
            ]
            
            feedback_counts = {}
            async for doc in db.feedback.aggregate(pipeline):
                key = f"{doc['_id']['drug_name']}|{doc['_id']['query']}"
                feedback_counts[key] = {
                    "drug_name": doc["_id"]["drug_name"],
                    "query": doc["_id"]["query"],
                    "helpful": doc["helpful"],
                    "not_helpful": doc["not_helpful"]
                }
            
            return feedback_counts
        except Exception as e:
            logger.error(f"Failed to get feedback counts: {e}")
            return {}
    
    async def get_ignored_medications(self, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get medications that should be ignored based on negative feedback."""
        try:
            db = await self.get_database()
            
            # Aggregate to find medications with high negative feedback ratio
            pipeline = [
                {
                    "$group": {
                        "_id": {"drug_name": "$drug_name", "query": "$query"},
                        "total_votes": {"$sum": 1},
                        "negative_votes": {"$sum": {"$cond": [{"$eq": ["$is_positive", False]}, 1, 0]}}
                    }
                },
                {
                    "$match": {"total_votes": {"$gte": 3}}  # Minimum votes
                }
            ]
            
            ignored = []
            async for doc in db.feedback.aggregate(pipeline):
                negative_ratio = doc["negative_votes"] / doc["total_votes"]
                if negative_ratio >= threshold:
                    ignored.append({
                        "drug_name": doc["_id"]["drug_name"],
                        "query": doc["_id"]["query"],
                        "negative_percentage": round(negative_ratio * 100, 2),
                        "total_votes": doc["total_votes"]
                    })
            
            return ignored
        except Exception as e:
            logger.error(f"Failed to get ignored medications: {e}")
            return []
    
    # Search Metrics Operations
    async def record_search_metric(self, query: str, results_count: int, response_time_ms: float,
                                  user_id: str = None, session_id: str = None,
                                  api_calls_count: int = 0, cache_hits: int = 0, cache_misses: int = 0):
        """Record search metric."""
        try:
            db = await self.get_database()
            metric = SearchMetricDocument(
                query=query,
                results_count=results_count,
                response_time_ms=response_time_ms,
                user_id=user_id,
                session_id=session_id,
                api_calls_count=api_calls_count,
                cache_hits=cache_hits,
                cache_misses=cache_misses
            )
            await db.search_metrics.insert_one(metric.dict(by_alias=True))
        except Exception as e:
            logger.error(f"Failed to record search metric: {e}")
    
    async def record_api_metric(self, api_name: str, endpoint: str, response_time_ms: float,
                               status_code: int = 200, success: bool = True,
                               search_query: str = None, results_count: int = 0):
        """Record API metric."""
        try:
            db = await self.get_database()
            metric = ApiMetricDocument(
                api_name=api_name,
                endpoint=endpoint,
                response_time_ms=response_time_ms,
                status_code=status_code,
                success=success,
                search_query=search_query,
                results_count=results_count
            )
            await db.api_metrics.insert_one(metric.dict(by_alias=True))
        except Exception as e:
            logger.error(f"Failed to record API metric: {e}")
    
    async def record_user_activity(self, action: str, user_id: str = None, 
                                  session_id: str = None, metadata: Dict[str, Any] = None):
        """Record user activity."""
        try:
            db = await self.get_database()
            activity = UserActivityDocument(
                action=action,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata
            )
            await db.user_activity.insert_one(activity.dict(by_alias=True))
        except Exception as e:
            logger.error(f"Failed to record user activity: {e}")
    
    async def get_metrics_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            db = await self.get_database()
            
            # Search metrics aggregation
            search_pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": None,
                        "total_searches": {"$sum": 1},
                        "avg_response_time": {"$avg": "$response_time_ms"},
                        "total_results": {"$sum": "$results_count"},
                        "avg_results_per_search": {"$avg": "$results_count"},
                        "unique_queries": {"$addToSet": "$query"},
                        "total_api_calls": {"$sum": "$api_calls_count"},
                        "total_cache_hits": {"$sum": "$cache_hits"},
                        "total_cache_misses": {"$sum": "$cache_misses"}
                    }
                }
            ]
            
            search_result = await db.search_metrics.aggregate(search_pipeline).to_list(1)
            search_stats = search_result[0] if search_result else {}
            
            # API metrics aggregation
            api_pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": None,
                        "total_api_calls": {"$sum": 1},
                        "avg_response_time": {"$avg": "$response_time_ms"},
                        "successful_calls": {"$sum": {"$cond": [{"$eq": ["$success", True]}, 1, 0]}},
                        "failed_calls": {"$sum": {"$cond": [{"$eq": ["$success", False]}, 1, 0]}},
                        "unique_apis": {"$addToSet": "$api_name"}
                    }
                }
            ]
            
            api_result = await db.api_metrics.aggregate(api_pipeline).to_list(1)
            api_stats = api_result[0] if api_result else {}
            
            # User activity aggregation
            activity_pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": None,
                        "total_activities": {"$sum": 1},
                        "unique_users": {"$addToSet": "$user_id"},
                        "unique_sessions": {"$addToSet": "$session_id"}
                    }
                }
            ]
            
            activity_result = await db.user_activity.aggregate(activity_pipeline).to_list(1)
            activity_stats = activity_result[0] if activity_result else {}
            
            # Top queries
            top_queries_pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff_time}}},
                {"$group": {"_id": "$query", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            
            top_queries = []
            async for doc in db.search_metrics.aggregate(top_queries_pipeline):
                top_queries.append({"query": doc["_id"], "count": doc["count"]})
            
            # API performance by service
            api_performance_pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": "$api_name",
                        "call_count": {"$sum": 1},
                        "avg_response_time": {"$avg": "$response_time_ms"},
                        "successful_calls": {"$sum": {"$cond": [{"$eq": ["$success", True]}, 1, 0]}}
                    }
                },
                {"$sort": {"call_count": -1}},
                {"$limit": 10}
            ]
            
            api_performance = []
            async for doc in db.api_metrics.aggregate(api_performance_pipeline):
                success_rate = (doc["successful_calls"] / doc["call_count"]) * 100 if doc["call_count"] > 0 else 0
                api_performance.append({
                    "api_name": doc["_id"],
                    "call_count": doc["call_count"],
                    "avg_response_time": round(doc["avg_response_time"] or 0, 2),
                    "success_rate": round(success_rate, 2)
                })
            
            return {
                "time_period_hours": time_period_hours,
                "search_metrics": {
                    "total_searches": search_stats.get("total_searches", 0),
                    "avg_response_time_ms": round(search_stats.get("avg_response_time", 0), 2),
                    "total_results": search_stats.get("total_results", 0),
                    "avg_results_per_search": round(search_stats.get("avg_results_per_search", 0), 2),
                    "unique_queries": len(search_stats.get("unique_queries", [])),
                    "total_api_calls": search_stats.get("total_api_calls", 0),
                    "cache_hit_rate": round(
                        (search_stats.get("total_cache_hits", 0) / 
                         (search_stats.get("total_cache_hits", 0) + search_stats.get("total_cache_misses", 0)) * 100), 2
                    ) if (search_stats.get("total_cache_hits", 0) + search_stats.get("total_cache_misses", 0)) > 0 else 0
                },
                "api_metrics": {
                    "total_api_calls": api_stats.get("total_api_calls", 0),
                    "avg_response_time_ms": round(api_stats.get("avg_response_time", 0), 2),
                    "success_rate": round((api_stats.get("successful_calls", 0) / api_stats.get("total_api_calls", 1)) * 100, 2),
                    "failed_calls": api_stats.get("failed_calls", 0),
                    "unique_apis": len(api_stats.get("unique_apis", []))
                },
                "user_activity": {
                    "total_activities": activity_stats.get("total_activities", 0),
                    "unique_users": len([u for u in activity_stats.get("unique_users", []) if u]),
                    "unique_sessions": len([s for s in activity_stats.get("unique_sessions", []) if s])
                },
                "top_queries": top_queries,
                "api_performance": api_performance,
                "timestamp": datetime.utcnow().timestamp()
            }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {
                "time_period_hours": time_period_hours,
                "error": str(e),
                "timestamp": datetime.utcnow().timestamp()
            }
    
    async def get_time_series_data(self, metric_type: str, time_period_hours: int = 24, 
                                  interval_hours: int = 1) -> List[Dict[str, Any]]:
        """Get time series data for charts."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)
            db = await self.get_database()
            
            # Create time buckets
            pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff_time}}},
                {
                    "$group": {
                        "_id": {
                            "$dateTrunc": {
                                "date": "$timestamp",
                                "unit": "hour",
                                "binSize": interval_hours
                            }
                        },
                        "count": {"$sum": 1},
                        "avg_response_time": {"$avg": "$response_time_ms"}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            collection_name = "search_metrics" if metric_type == "searches" else "api_metrics"
            data_points = []
            
            async for doc in db[collection_name].aggregate(pipeline):
                data_points.append({
                    "timestamp": int(doc["_id"].timestamp()),
                    "count": doc["count"],
                    "avg_response_time": round(doc["avg_response_time"] or 0, 2)
                })
            
            return data_points
        except Exception as e:
            logger.error(f"Failed to get time series data: {e}")
            return []
    
    async def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old data to prevent database bloat."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=days_to_keep)
            db = await self.get_database()
            
            # Delete old records from all collections
            collections = ["feedback", "search_metrics", "api_metrics", "system_metrics", "user_activity"]
            deleted_count = 0
            
            for collection_name in collections:
                result = await db[collection_name].delete_many({
                    "timestamp": {"$lt": cutoff_time}
                })
                deleted_count += result.deleted_count
            
            logger.info(f"Cleaned up {deleted_count} old records")
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")

# Global MongoDB manager instance
mongodb_manager = MongoDBManager()
