"""
Analytics Database Manager for RxVerify

This module handles persistent storage of all analytics and metrics data
for the admin dashboard, including request metrics, activity logs, and performance data.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import IndexModel, ASCENDING, DESCENDING
from pydantic import BaseModel
from app.mongodb_config import MongoDBConfig

logger = logging.getLogger(__name__)


class RequestLog(BaseModel):
    """Individual request log entry."""
    timestamp: datetime
    endpoint: str
    query: Optional[str] = None
    success: bool
    response_time_ms: float
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class HourlyMetrics(BaseModel):
    """Hourly aggregated metrics."""
    hour: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_response_time_ms: float
    average_response_time_ms: float
    success_rate: float


class DailyMetrics(BaseModel):
    """Daily aggregated metrics."""
    date: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_response_time_ms: float
    average_response_time_ms: float
    success_rate: float
    unique_queries: int
    top_queries: List[Dict[str, Any]]


class AnalyticsDatabaseManager:
    """Manages analytics and metrics data in MongoDB."""
    
    def __init__(self):
        self.mongodb_config = MongoDBConfig()
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.request_logs_collection: Optional[AsyncIOMotorCollection] = None
        self.hourly_metrics_collection: Optional[AsyncIOMotorCollection] = None
        self.daily_metrics_collection: Optional[AsyncIOMotorCollection] = None
        self.system_stats_collection: Optional[AsyncIOMotorCollection] = None
    
    async def initialize(self):
        """Initialize MongoDB connection and collections."""
        try:
            self.db = await self.mongodb_config.connect()
            self.client = self.mongodb_config.client
            self.request_logs_collection = self.db.analytics_request_logs
            self.hourly_metrics_collection = self.db.analytics_hourly_metrics
            self.daily_metrics_collection = self.db.analytics_daily_metrics
            self.system_stats_collection = self.db.analytics_system_stats
            
            # Create indexes for fast querying
            await self._create_indexes()
            
            logger.info("Analytics database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize analytics database manager: {str(e)}")
            raise
    
    async def _create_indexes(self):
        """Create MongoDB indexes for optimal query performance."""
        try:
            # Request logs indexes
            await self.request_logs_collection.create_indexes([
                IndexModel([("timestamp", DESCENDING)]),
                IndexModel([("endpoint", ASCENDING)]),
                IndexModel([("success", ASCENDING)]),
                IndexModel([("timestamp", ASCENDING), ("endpoint", ASCENDING)])
            ])
            
            # Hourly metrics indexes
            await self.hourly_metrics_collection.create_indexes([
                IndexModel([("hour", DESCENDING)]),
                IndexModel([("hour", ASCENDING)])
            ])
            
            # Daily metrics indexes
            await self.daily_metrics_collection.create_indexes([
                IndexModel([("date", DESCENDING)]),
                IndexModel([("date", ASCENDING)])
            ])
            
            # System stats indexes
            await self.system_stats_collection.create_indexes([
                IndexModel([("type", ASCENDING)], unique=True)
            ])
            
            logger.info("Analytics database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create analytics indexes: {str(e)}")
            raise
    
    async def log_request(self, endpoint: str, query: Optional[str] = None, 
                         success: bool = True, response_time_ms: float = 0.0,
                         ip_address: Optional[str] = None, user_agent: Optional[str] = None):
        """Log a request to the analytics database."""
        try:
            request_log = RequestLog(
                timestamp=datetime.utcnow(),
                endpoint=endpoint,
                query=query,
                success=success,
                response_time_ms=response_time_ms,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            await self.request_logs_collection.insert_one(request_log.dict())
            
            # Trigger hourly aggregation if needed
            await self._aggregate_hourly_metrics_if_needed()
            
        except Exception as e:
            logger.error(f"Failed to log request: {str(e)}")
    
    async def _aggregate_hourly_metrics_if_needed(self):
        """Aggregate hourly metrics if the current hour hasn't been processed yet."""
        try:
            now = datetime.utcnow()
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            
            # Check if we already have metrics for this hour
            existing = await self.hourly_metrics_collection.find_one({
                "hour": current_hour
            })
            
            if existing:
                return  # Already aggregated
            
            # Get all requests for this hour
            hour_start = current_hour
            hour_end = current_hour + timedelta(hours=1)
            
            pipeline = [
                {
                    "$match": {
                        "timestamp": {
                            "$gte": hour_start,
                            "$lt": hour_end
                        }
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_requests": {"$sum": 1},
                        "successful_requests": {
                            "$sum": {"$cond": ["$success", 1, 0]}
                        },
                        "failed_requests": {
                            "$sum": {"$cond": ["$success", 0, 1]}
                        },
                        "total_response_time_ms": {"$sum": "$response_time_ms"},
                        "average_response_time_ms": {"$avg": "$response_time_ms"}
                    }
                }
            ]
            
            result = await self.request_logs_collection.aggregate(pipeline).to_list(1)
            
            if result:
                data = result[0]
                success_rate = (data["successful_requests"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                
                hourly_metrics = HourlyMetrics(
                    hour=current_hour,
                    total_requests=data["total_requests"],
                    successful_requests=data["successful_requests"],
                    failed_requests=data["failed_requests"],
                    total_response_time_ms=data["total_response_time_ms"],
                    average_response_time_ms=data["average_response_time_ms"] or 0,
                    success_rate=success_rate
                )
                
                await self.hourly_metrics_collection.insert_one(hourly_metrics.dict())
                
        except Exception as e:
            logger.error(f"Failed to aggregate hourly metrics: {str(e)}")
    
    async def get_recent_requests(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent request logs for the admin dashboard."""
        try:
            cursor = self.request_logs_collection.find({}).sort("timestamp", DESCENDING).limit(limit)
            requests = []
            
            async for request in cursor:
                requests.append({
                    "timestamp": request["timestamp"].timestamp(),
                    "time_formatted": request["timestamp"].strftime("%I:%M:%S %p"),
                    "endpoint": request["endpoint"],
                    "type": self._get_request_type(request["endpoint"]),
                    "query": request.get("query", ""),
                    "success": request["success"],
                    "response_time_ms": request["response_time_ms"],
                    "response_time_formatted": f"{request['response_time_ms']/1000:.1f}s"
                })
            
            return requests
            
        except Exception as e:
            logger.error(f"Failed to get recent requests: {str(e)}")
            return []
    
    def _get_request_type(self, endpoint: str) -> str:
        """Get request type based on endpoint."""
        if "/drugs/search" in endpoint:
            return "Search"
        elif "/query" in endpoint:
            return "Query"
        elif "/feedback" in endpoint:
            return "Feedback"
        elif "/vote" in endpoint:
            return "Vote"
        else:
            return "API Call"
    
    async def get_metrics_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive metrics summary from the database."""
        try:
            end_time = datetime.utcnow()
            if time_period_hours is None or time_period_hours <= 0:
                start_time = datetime.utcfromtimestamp(0)
            else:
                start_time = end_time - timedelta(hours=time_period_hours)
            
            lifetime_total = await self.request_logs_collection.count_documents({})
            
            # Get aggregated metrics from hourly data
            pipeline = [
                {
                    "$match": {
                        "hour": {
                            "$gte": start_time,
                            "$lte": end_time
                        }
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_requests": {"$sum": "$total_requests"},
                        "successful_requests": {"$sum": "$successful_requests"},
                        "failed_requests": {"$sum": "$failed_requests"},
                        "total_response_time_ms": {"$sum": "$total_response_time_ms"},
                        "average_response_time_ms": {"$avg": "$average_response_time_ms"}
                    }
                }
            ]
            
            result = await self.hourly_metrics_collection.aggregate(pipeline).to_list(1)
            
            if result:
                data = result[0]
                success_rate = (data["successful_requests"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                error_rate = (data["failed_requests"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                avg_response_time = data["average_response_time_ms"] or 0
                
                return {
                    "total_requests": data["total_requests"],
                    "successful_requests": data["successful_requests"],
                    "failed_requests": data["failed_requests"],
                    "success_rate": round(success_rate, 2),
                    "error_rate": round(error_rate, 2),
                    "average_response_time_ms": round(avg_response_time, 2),
                    "time_period_hours": time_period_hours if time_period_hours > 0 else 0,
                    "lifetime_requests": lifetime_total
                }
            else:
                realtime_metrics = await self._calculate_realtime_metrics(start_time, end_time)
                realtime_metrics["lifetime_requests"] = lifetime_total
                realtime_metrics["time_period_hours"] = time_period_hours if time_period_hours > 0 else 0
                return realtime_metrics
                
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {str(e)}")
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "error_rate": 0.0,
                "average_response_time_ms": 0.0,
                "time_period_hours": time_period_hours,
                "lifetime_requests": 0
            }
    
    async def _calculate_realtime_metrics(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Calculate metrics from raw request logs."""
        try:
            pipeline = [
                {
                    "$match": {
                        "timestamp": {
                            "$gte": start_time,
                            "$lte": end_time
                        }
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_requests": {"$sum": 1},
                        "successful_requests": {
                            "$sum": {"$cond": ["$success", 1, 0]}
                        },
                        "failed_requests": {
                            "$sum": {"$cond": ["$success", 0, 1]}
                        },
                        "average_response_time_ms": {"$avg": "$response_time_ms"}
                    }
                }
            ]
            
            result = await self.request_logs_collection.aggregate(pipeline).to_list(1)
            
            if result:
                data = result[0]
                success_rate = (data["successful_requests"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                error_rate = (data["failed_requests"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                
                return {
                    "total_requests": data["total_requests"],
                    "successful_requests": data["successful_requests"],
                    "failed_requests": data["failed_requests"],
                    "success_rate": round(success_rate, 2),
                    "error_rate": round(error_rate, 2),
                    "average_response_time_ms": round(data["average_response_time_ms"] or 0, 2),
                    "time_period_hours": int((end_time - start_time).total_seconds() / 3600)
                }
            else:
                return {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "average_response_time_ms": 0.0,
                    "time_period_hours": int((end_time - start_time).total_seconds() / 3600)
                }
                
        except Exception as e:
            logger.error(f"Failed to calculate realtime metrics: {str(e)}")
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "error_rate": 0.0,
                "average_response_time_ms": 0.0,
                "time_period_hours": int((end_time - start_time).total_seconds() / 3600)
            }
    
    async def get_time_series_data(self, metric_type: str = "searches", 
                                 time_period_hours: int = 24, 
                                 interval_hours: int = 1) -> List[Dict[str, Any]]:
        """Get time series data for charts."""
        try:
            if self.request_logs_collection is None or self.hourly_metrics_collection is None:
                await self.initialize()
            
            if time_period_hours is None or time_period_hours <= 0:
                if metric_type == "searches":
                    return await self._get_search_trends(days=7)
                time_period_hours = 24 * 7
            
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=time_period_hours)
            
            # Get hourly metrics data
            cursor = self.hourly_metrics_collection.find({
                "hour": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }).sort("hour", ASCENDING)
            
            data_points = []
            async for metrics in cursor:
                data_points.append({
                    "timestamp": metrics["hour"].timestamp(),
                    "count": metrics["total_requests"]
                })
            
            return data_points
            
        except Exception as e:
            logger.error(f"Failed to get time series data: {str(e)}")
            return []
    
    async def _get_search_trends(self, days: int = 7) -> List[Dict[str, Any]]:
        """Aggregate total requests per day for the given window."""
        try:
            if self.request_logs_collection is None:
                await self.initialize()
            
            end_time = datetime.utcnow()
            end_date = end_time.date()
            start_date = (end_time - timedelta(days=days - 1)).date()
            start_time = datetime.combine(start_date, datetime.min.time())
            pipeline = [
                {
                    "$match": {
                        "timestamp": {
                            "$gte": start_time
                        }
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$timestamp"
                            }
                        },
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            results = await self.request_logs_collection.aggregate(pipeline).to_list(None)
            
            counts_by_date: Dict[str, int] = {}
            for doc in results:
                counts_by_date[doc["_id"]] = doc["count"]
            
            data_points: List[Dict[str, Any]] = []
            for i in range(days):
                day = start_date + timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                count = counts_by_date.get(day_str, 0)
                dt = datetime.combine(day, datetime.min.time())
                data_points.append({
                    "timestamp": dt.timestamp(),
                    "count": count
                })
            
            return data_points
        except Exception as e:
            logger.error(f"Failed to get search trends: {str(e)}")
            return []
    
    async def upsert_rxlist_stats(self, total_drugs: int) -> Dict[str, Any]:
        """Update and return RxList database statistics."""
        try:
            if self.system_stats_collection is None:
                await self.initialize()
            
            now = datetime.utcnow()
            existing = await self.system_stats_collection.find_one({"type": "rxlist_stats"})
            
            if existing and existing.get("total_drugs") == total_drugs:
                return existing
            
            previous_total = existing.get("total_drugs") if existing else total_drugs
            
            update_doc = {
                "type": "rxlist_stats",
                "total_drugs": total_drugs,
                "previous_total": previous_total,
                "delta": total_drugs - previous_total,
                "updated_at": now,
                "previous_updated_at": existing.get("updated_at") if existing else now
            }
            update_doc["timezone"] = "UTC"
            
            await self.system_stats_collection.update_one(
                {"type": "rxlist_stats"},
                {"$set": update_doc},
                upsert=True
            )
            
            return update_doc
        except Exception as e:
            logger.error(f"Failed to upsert RxList stats: {str(e)}")
            # Return a best-effort document
            fallback_now = datetime.utcnow()
            return existing or {
                "type": "rxlist_stats",
                "total_drugs": total_drugs,
                "previous_total": total_drugs,
                "delta": 0,
                "updated_at": fallback_now,
                "previous_updated_at": fallback_now
            }
    
    async def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old analytics data to prevent database bloat."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            # Delete old request logs
            result_logs = await self.request_logs_collection.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            # Delete old hourly metrics (keep daily aggregates)
            cutoff_hourly = datetime.utcnow() - timedelta(days=7)  # Keep hourly for 7 days
            result_hourly = await self.hourly_metrics_collection.delete_many({
                "hour": {"$lt": cutoff_hourly}
            })
            
            logger.info(f"Cleaned up analytics data: {result_logs.deleted_count} logs, {result_hourly.deleted_count} hourly metrics")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old analytics data: {str(e)}")


# Global analytics manager instance
analytics_db_manager = AnalyticsDatabaseManager()
