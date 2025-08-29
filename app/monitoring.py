"""Monitoring and health check functionality for MedRAG."""
import time
from typing import Dict, Any
from app.db import get_collection
from app.embeddings import embed
from app.logging import get_logger

logger = get_logger(__name__)

class SystemMonitor:
    """Monitor system health and performance."""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
    
    def record_request(self, success: bool = True):
        """Record a request for monitoring."""
        self.request_count += 1
        if not success:
            self.error_count += 1
    
    def get_uptime(self) -> float:
        """Get system uptime in seconds."""
        return time.time() - self.start_time
    
    def get_success_rate(self) -> float:
        """Get request success rate."""
        if self.request_count == 0:
            return 100.0
        return ((self.request_count - self.error_count) / self.request_count) * 100

# Global monitor instance
monitor = SystemMonitor()

async def check_chromadb_health() -> Dict[str, Any]:
    """Check ChromaDB health and status."""
    try:
        collection = get_collection()
        count = collection.count()
        
        # Test a simple search
        test_results = collection.query(
            query_texts=["test"],
            n_results=1
        )
        
        return {
            "status": "healthy",
            "document_count": count,
            "search_functional": len(test_results.get('documents', [])) > 0,
            "collection_name": collection.name
        }
    except Exception as e:
        logger.error(f"ChromaDB health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

async def check_embeddings_health() -> Dict[str, Any]:
    """Check embedding service health."""
    try:
        start_time = time.time()
        test_embedding = await embed(["test"])
        processing_time = time.time() - start_time
        
        return {
            "status": "healthy",
            "embedding_dimensions": len(test_embedding[0]),
            "processing_time_ms": round(processing_time * 1000, 2)
        }
    except Exception as e:
        logger.error(f"Embeddings health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

async def get_system_status() -> Dict[str, Any]:
    """Get comprehensive system status."""
    chromadb_status = await check_chromadb_health()
    embeddings_status = await check_embeddings_health()
    
    return {
        "timestamp": time.time(),
        "uptime_seconds": monitor.get_uptime(),
        "request_count": monitor.request_count,
        "error_count": monitor.error_count,
        "success_rate_percent": monitor.get_success_rate(),
        "chromadb": chromadb_status,
        "embeddings": embeddings_status,
        "overall_status": "healthy" if (
            chromadb_status["status"] == "healthy" and 
            embeddings_status["status"] == "healthy"
        ) else "degraded"
    }
