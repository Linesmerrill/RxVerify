"""
Simple Monitoring System for RxVerify

Tracks request metrics, response times, and system performance.
Now integrates with persistent analytics database.
"""

import time
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)


class SimpleMonitor:
    """Simple in-memory monitoring system for tracking metrics with persistent storage."""
    
    def __init__(self, broadcast_callback=None, analytics_db_manager=None):
        self._lock = threading.Lock()
        self.broadcast_callback = broadcast_callback
        self.analytics_db_manager = analytics_db_manager
        self._reset_metrics()
    
    def _reset_metrics(self):
        """Reset all metrics to initial state."""
        with self._lock:
            self.total_requests = 0
            self.successful_requests = 0
            self.failed_requests = 0
            self.response_times = deque(maxlen=1000)  # Keep last 1000 response times
            self.request_history = deque(maxlen=1000)  # Keep last 1000 requests
            self.hourly_stats = defaultdict(lambda: {
                'requests': 0,
                'successful': 0,
                'failed': 0,
                'total_response_time': 0.0
            })
    
    def record_request(self, success: bool, response_time_ms: float = 0.0, endpoint: str = "unknown", query: str = None):
        """Record a request with its outcome and response time."""
        with self._lock:
            self.total_requests += 1
            
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            
            if response_time_ms > 0:
                self.response_times.append(response_time_ms)
            
            # Record request details
            request_record = {
                'timestamp': time.time(),
                'success': success,
                'response_time_ms': response_time_ms,
                'endpoint': endpoint,
                'query': query
            }
            self.request_history.append(request_record)
            
            # Update hourly stats
            hour_key = datetime.now().strftime('%Y-%m-%d-%H')
            self.hourly_stats[hour_key]['requests'] += 1
            if success:
                self.hourly_stats[hour_key]['successful'] += 1
            else:
                self.hourly_stats[hour_key]['failed'] += 1
            self.hourly_stats[hour_key]['total_response_time'] += response_time_ms
            
            # Broadcast real-time update if callback is available
            if self.broadcast_callback:
                try:
                    # Calculate current metrics for broadcast
                    success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
                    avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
                    
                    broadcast_data = {
                        "type": "metrics_update",
                        "data": {
                            "total_requests": self.total_requests,
                            "success_rate": round(success_rate, 2),
                            "average_response_time": round(avg_response_time, 2),
                            "recent_activity": {
                                "query": query,
                                "endpoint": endpoint,
                                "success": success,
                                "response_time_ms": response_time_ms,
                                "timestamp": request_record['timestamp']
                            }
                        }
                    }
                    # Schedule broadcast in a separate task to avoid blocking
                    import asyncio
                    asyncio.create_task(self.broadcast_callback(broadcast_data))
                except Exception as e:
                    logger.warning(f"Failed to broadcast metrics update: {e}")
            
            # Save to persistent analytics database
            if self.analytics_db_manager:
                try:
                    import asyncio
                    asyncio.create_task(self.analytics_db_manager.log_request(
                        endpoint=endpoint,
                        query=query,
                        success=success,
                        response_time_ms=response_time_ms
                    ))
                except Exception as e:
                    logger.warning(f"Failed to log request to analytics database: {e}")
    
    def get_metrics_summary(self, time_period_hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        with self._lock:
            # Calculate success rate
            success_rate = 0.0
            if self.total_requests > 0:
                success_rate = (self.successful_requests / self.total_requests) * 100
            
            # Calculate average response time
            avg_response_time = 0.0
            if self.response_times:
                avg_response_time = sum(self.response_times) / len(self.response_times)
            
            # Calculate error rate
            error_rate = 0.0
            if self.total_requests > 0:
                error_rate = (self.failed_requests / self.total_requests) * 100
            
            # Get recent activity (last 24 hours)
            cutoff_time = time.time() - (time_period_hours * 3600)
            recent_requests = [
                req for req in self.request_history 
                if req['timestamp'] >= cutoff_time
            ]
            
            recent_successful = sum(1 for req in recent_requests if req['success'])
            recent_total = len(recent_requests)
            recent_success_rate = (recent_successful / recent_total * 100) if recent_total > 0 else 0.0
            
            return {
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'success_rate': round(success_rate, 2),
                'error_rate': round(error_rate, 2),
                'average_response_time_ms': round(avg_response_time, 2),
                'recent_requests_24h': recent_total,
                'recent_success_rate_24h': round(recent_success_rate, 2),
                'time_period_hours': time_period_hours
            }
    
    def get_time_series_data(self, metric_type: str = "searches", time_period_hours: int = 24, interval_hours: int = 1) -> List[Dict[str, Any]]:
        """Get time series data for charts."""
        with self._lock:
            data_points = []
            current_time = time.time()
            start_time = current_time - (time_period_hours * 3600)
            
            # Generate time buckets
            bucket_size = interval_hours * 3600  # Convert to seconds
            current_bucket = start_time
            
            while current_bucket < current_time:
                bucket_end = current_bucket + bucket_size
                
                # Count requests in this time bucket
                bucket_requests = [
                    req for req in self.request_history
                    if current_bucket <= req['timestamp'] < bucket_end
                ]
                
                if metric_type == "searches":
                    count = len(bucket_requests)
                elif metric_type == "api_calls":
                    count = len(bucket_requests)  # Same as searches for now
                else:
                    count = 0
                
                data_points.append({
                    'timestamp': current_bucket,
                    'count': count
                })
                
                current_bucket = bucket_end
            
            return data_points
    
    def get_recent_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent request history."""
        with self._lock:
            recent_requests = list(self.request_history)[-limit:]
            # Format for frontend display
            formatted_requests = []
            for req in recent_requests:
                formatted_requests.append({
                    "timestamp": req["timestamp"],
                    "time_formatted": datetime.fromtimestamp(req["timestamp"]).strftime("%I:%M:%S %p"),
                    "endpoint": req["endpoint"],
                    "type": self._get_request_type(req["endpoint"]),
                    "query": self._get_query_from_endpoint(req),
                    "success": req["success"],
                    "response_time_ms": req["response_time_ms"],
                    "response_time_formatted": f"{req['response_time_ms']/1000:.1f}s"
                })
            return formatted_requests
    
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
    
    def _get_query_from_endpoint(self, req: Dict[str, Any]) -> str:
        """Extract query from request for display."""
        if req.get('query'):
            return req['query']
        
        # Fallback based on endpoint
        endpoint = req.get('endpoint', '')
        if "/drugs/search" in endpoint:
            return "Drug search query"
        elif "/query" in endpoint:
            return "General query"
        elif "/feedback" in endpoint:
            return "Feedback submission"
        elif "/vote" in endpoint:
            return "Drug vote"
        else:
            return endpoint
    
    def reset_metrics(self):
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._reset_metrics()
            logger.info("Monitoring metrics reset")


# Global monitor instance
monitor = SimpleMonitor()
