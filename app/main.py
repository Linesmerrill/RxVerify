from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import time
from typing import List, Dict, Optional
from datetime import datetime
from app.retriever import retrieve
from app.crosscheck import unify_with_crosscheck
from app.llm import generate_drug_response
from app.monitoring import monitor, get_system_status
from app.logging import logger
from app.config import settings
from app.medical_apis import close_medical_api_client
from app.search_service import get_search_service
from app.medication_cache import get_medication_cache
from app.rxlist_database import get_rxlist_database
from app.post_discharge_search import get_post_discharge_search_service
from app.metrics_database import MetricsDatabase
# Import database manager based on environment
if 'MONGODB_URI' in os.environ or 'MONGODB_URL' in os.environ:
    from app.mongodb_manager import mongodb_manager as db_manager
else:
    from app.database_manager import db_manager
from app.models import (
    RetrievedDoc, SearchRequest, DrugSearchResult, SearchResponse,
    FeedbackRequest, FeedbackResponse, MLPipelineUpdate, Source
)

# Validate settings
settings.validate()

# Initialize metrics database
metrics_db = MetricsDatabase()

app = FastAPI(
    title="RxVerify - Multi-Database Drug Assistant",
    description="Real-time Retrieval-Augmented Generation system for drug information from RxNorm, DailyMed, OpenFDA, and DrugBank",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket functionality temporarily removed to fix server crashes

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    # Disable ChromaDB telemetry to reduce log noise
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    
    logger.info("🚀 RxVerify starting up - Real-time medical database integration enabled")
    
    # Initialize database tables/collections
    try:
        # Check if MongoDB is configured
        if 'MONGODB_URI' in os.environ or 'MONGODB_URL' in os.environ:
            logger.info("MongoDB detected - initializing MongoDB collections")
            await db_manager.create_indexes()
            logger.info("✅ MongoDB collections initialized successfully")
        else:
            logger.info("SQL/PostgreSQL detected - initializing database tables")
            db_manager.create_tables()
            logger.info("✅ Database tables initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("🛑 RxVerify shutting down - cleaning up medical API client")
    await close_medical_api_client()

class Query(BaseModel):
    question: str
    top_k: int = 6

class QueryResponse(BaseModel):
    answer: str
    context: dict
    processing_time_ms: float
    sources_consulted: list
    sources: list  # Individual source documents
    cross_validation: list  # Cross-validation findings
    search_debug: dict  # Search debugging information


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

@app.get("/health")
async def health():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": time.time()}

# WebSocket endpoint temporarily removed to fix server crashes

@app.get("/socket.io/")
async def socket_io_fallback():
    """Handle Socket.IO requests gracefully to prevent 404 errors."""
    return JSONResponse(
        status_code=200,
        content={"message": "Socket.IO not configured - using REST API instead"}
    )

@app.get("/socket.io/{path:path}")
async def socket_io_fallback_path(path: str):
    """Handle Socket.IO requests with any path gracefully to prevent 404 errors."""
    return JSONResponse(
        status_code=200,
        content={"message": "Socket.IO not configured - using REST API instead", "path": path}
    )

@app.get("/cache/stats")
async def get_cache_stats():
    """Get medication cache statistics."""
    try:
        cache = get_medication_cache()
        stats = cache.get_cache_stats()
        return {
            "status": "success",
            "cache_stats": stats,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")

@app.post("/cache/clear")
async def clear_cache():
    """Clear the medication cache."""
    try:
        cache = get_medication_cache()
        success = cache.clear_cache()
        if success:
            return {"status": "success", "message": "Cache cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear cache")
    except Exception as e:
        logger.error(f"Failed to clear cache: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

@app.get("/status")
async def status():
    """Comprehensive system status endpoint."""
    return await get_system_status()

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "RxVerify - Multi-Database Drug Assistant",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "status": "/status"
    }

@app.post("/query", response_model=QueryResponse)
async def query(q: Query, request: Request):
    """Main query endpoint for drug information."""
    start_time = time.time()
    
    try:
        logger.info(f"Processing query: {q.question[:100]}...")
        
        # 1) Retrieve candidates from all sources (semantic + keyword)
        search_start = time.time()
        docs = await retrieve(q.question, top_k=q.top_k)
        search_time = (time.time() - search_start) * 1000
        logger.info(f"Retrieved {len(docs)} documents")
        
        # 2) Cross‑check & unify fields; produce structured context + citations
        context = unify_with_crosscheck(docs)
        logger.info(f"Cross-check completed, {len(context.get('records', []))} unified records")
        
        # 3) Call real LLM for intelligent response generation
        answer = await generate_drug_response(q.question, context)
        logger.info("LLM response generated successfully")
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Record successful request
        monitor.record_request(success=True)
        
        # Extract sources consulted
        sources_consulted = list(set([
            doc.source.value for doc in docs
        ]))
        
        # Prepare sources for frontend display
        sources = []
        for doc in docs:
            sources.append({
                "source": doc.source.value,
                "rxcui": doc.rxcui,
                "id": doc.id,
                "url": doc.url,
                "title": doc.title,
                "text": doc.text,
                "score": getattr(doc, 'score', None)  # Vector similarity score if available
            })
        
        # Extract cross-validation findings
        cross_validation = context.get('disagreements', [])
        
        # Prepare search debug information
        search_debug = {
            "query": q.question,
            "strategy": "Real-time Medical Database APIs",
            "total_retrieved": len(docs),
            "search_time_ms": round(search_time, 2),
            "top_k": q.top_k,
            "sources_queried": ["RxNorm", "DailyMed", "OpenFDA", "DrugBank"],
            "retrieval_method": "Live API calls to medical databases"
        }
        
        return QueryResponse(
            answer=answer,
            context=context,
            processing_time_ms=round(processing_time, 2),
            sources_consulted=sources_consulted,
            sources=sources,
            cross_validation=cross_validation,
            search_debug=search_debug
        )
        
    except Exception as e:
        # Record failed request
        monitor.record_request(success=False)
        
        logger.error(f"Query processing failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Query processing failed: {str(e)}"
        )

@app.post("/search", response_model=SearchResponse)
async def search_medications(request: SearchRequest):
    """Enhanced medication search endpoint for post-discharge medications."""
    start_time = time.time()
    
    try:
        logger.info(f"Processing enhanced medication search: {request.query[:50]}...")
        
        # Add timeout for the search operation
        import asyncio
        search_service = await get_post_discharge_search_service()
        search_task = asyncio.create_task(
            search_service.search_discharge_medications(request.query, request.limit)
        )
        
        try:
            # Wait for search with 30 second timeout
            results = await asyncio.wait_for(search_task, timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"Search timeout for query: {request.query}")
            raise HTTPException(status_code=408, detail="Search request timed out")
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Record successful request
        monitor.record_request(success=True)
        
        # Record search metrics
        await metrics_db.record_search_metric(
            query=request.query,
            results_count=len(results),
            response_time_ms=processing_time,
            user_id=getattr(request, 'user_id', None),
            session_id=getattr(request, 'session_id', None)
        )
        
        # Record user activity
        await metrics_db.record_user_activity(
            action="medication_search",
            user_id=getattr(request, 'user_id', None),
            session_id=getattr(request, 'session_id', None),
            meta_data={"query_length": len(request.query), "results_count": len(results)}
        )
        
        # Convert results to dict format for JSON response
        results_dict = []
        for result in results:
            results_dict.append({
                "rxcui": result.rxcui,
                "name": result.name,
                "generic_name": result.generic_name,
                "brand_names": result.brand_names,
                "common_uses": result.common_uses,
                "drug_class": result.drug_class,
                "source": result.source,
                "feedback_score": getattr(result, 'feedback_score', None),
                "is_oral_medication": getattr(result, 'is_oral_medication', True),
                "discharge_relevance_score": getattr(result, 'discharge_relevance_score', None),
                "helpful_count": getattr(result, 'helpful_count', 0),
                "not_helpful_count": getattr(result, 'not_helpful_count', 0),
                "all_rxcuis": getattr(result, 'all_rxcuis', [])
            })
        
        return SearchResponse(
            results=results_dict,
            total_found=len(results),
            processing_time_ms=round(processing_time, 2)
        )
        
    except Exception as e:
        # Record failed request
        monitor.record_request(success=False)
        
        # Record failed search metrics
        processing_time = (time.time() - start_time) * 1000
        await metrics_db.record_search_metric(
            query=request.query,
            results_count=0,
            response_time_ms=processing_time,
            user_id=getattr(request, 'user_id', None),
            session_id=getattr(request, 'session_id', None)
        )
        
        # Record user activity
        await metrics_db.record_user_activity(
            action="medication_search_failed",
            user_id=getattr(request, 'user_id', None),
            session_id=getattr(request, 'session_id', None),
            meta_data={"error": str(e)[:100]}
        )
        
        logger.error(f"Enhanced medication search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Enhanced medication search failed: {str(e)}"
        )

@app.get("/rxlist/stats")
async def get_rxlist_stats():
    """Get RxList database statistics."""
    try:
        rxlist_db = get_rxlist_database()
        stats = rxlist_db.get_drug_stats()
        return {
            "status": "success",
            "rxlist_stats": stats,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to get RxList stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get RxList stats: {str(e)}")

@app.post("/rxlist/clear")
async def clear_rxlist_database():
    """Clear the RxList database."""
    try:
        rxlist_db = get_rxlist_database()
        success = rxlist_db.clear_database()
        if success:
            return {"status": "success", "message": "RxList database cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear RxList database")
    except Exception as e:
        logger.error(f"Failed to clear RxList database: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear RxList database: {str(e)}")

@app.post("/rxlist/ingest")
async def ingest_rxlist_data(drug_data: List[Dict]):
    """Ingest scraped RxList drug data into the database."""
    try:
        rxlist_db = get_rxlist_database()
        inserted_count = 0
        skipped_count = 0
        
        for drug in drug_data:
            try:
                success = rxlist_db.add_drug(
                    name=drug.get('name'),
                    generic_name=drug.get('generic_name'),
                    brand_names=drug.get('brand_names', []),
                    drug_class=drug.get('drug_class'),
                    common_uses=drug.get('common_uses', []),
                    description=drug.get('description'),
                    search_terms=drug.get('search_terms', [])
                )
                if success:
                    inserted_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                logger.error(f"Error ingesting drug {drug.get('name', 'unknown')}: {str(e)}")
                skipped_count += 1
        
        stats = rxlist_db.get_drug_stats()
        return {
            "status": "success",
            "message": f"Ingested {inserted_count} drugs, skipped {skipped_count} duplicates",
            "total_drugs": stats['total_drugs'],
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to ingest RxList data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest RxList data: {str(e)}")

@app.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest):
    """Submit user feedback for search results to improve ML pipeline."""
    try:
        is_removal = getattr(feedback, 'is_removal', False)
        action = "removing" if is_removal else "adding"
        vote_type = "positive" if feedback.is_positive else "negative"
        logger.info(f"Processing feedback for {feedback.drug_name}: {action} {vote_type} vote")
        
        # Get the post-discharge search service
        search_service = await get_post_discharge_search_service()
        
        # Record the feedback (with removal flag)
        search_service.record_feedback(feedback.drug_name, feedback.query, feedback.is_positive, is_removal)
        
        # Get updated counts
        feedback_counts = search_service.get_feedback_counts(feedback.drug_name, feedback.query)
        
        # Record successful request
        monitor.record_request(success=True)
        
        action_message = "removed" if is_removal else "recorded"
        return FeedbackResponse(
            success=True,
            message=f"Feedback {action_message} successfully for {feedback.drug_name}",
            updated_score=None  # No longer using scores
        )
        
    except Exception as e:
        # Record failed request
        monitor.record_request(success=False)
        
        logger.error(f"Feedback submission failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Feedback submission failed: {str(e)}"
        )

@app.get("/metrics/summary")
async def get_metrics_summary(time_period_hours: int = 24):
    """Get comprehensive system metrics summary."""
    try:
        summary = await metrics_db.get_metrics_summary(time_period_hours)
        return {
            "success": True,
            "data": summary,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to get metrics summary: {str(e)}")
        return {"success": False, "message": str(e)}

@app.get("/metrics/time-series")
async def get_time_series_data(metric_type: str = "searches", time_period_hours: int = 24, interval_hours: int = 1):
    """Get time series data for charts."""
    try:
        if metric_type not in ["searches", "api_calls"]:
            return {"success": False, "message": "Invalid metric_type. Must be 'searches' or 'api_calls'"}
        
        data = await metrics_db.get_time_series_data(metric_type, time_period_hours, interval_hours)
        return {
            "success": True,
            "data": data,
            "metric_type": metric_type,
            "time_period_hours": time_period_hours,
            "interval_hours": interval_hours,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to get time series data: {str(e)}")
        return {"success": False, "message": str(e)}

@app.get("/feedback/stats")
async def get_feedback_stats(time_period_hours: int = 24):
    """Get feedback statistics for ML pipeline monitoring."""
    try:
        search_service = await get_post_discharge_search_service()
        
        # Get feedback statistics from database with error handling
        try:
            stats = await search_service._feedback_db.get_feedback_stats()
        except Exception as e:
            logger.error(f"Error getting feedback stats: {e}")
            stats = {
                "total_feedback": 0,
                "total_helpful": 0,
                "total_not_helpful": 0,
                "recent_feedback_24h": 0,
                "helpful_percentage": 0
            }
        
        try:
            feedback_counts = await search_service._feedback_db.get_all_feedback_counts()
        except Exception as e:
            logger.error(f"Error getting feedback counts: {e}")
            feedback_counts = {}
        
        try:
            feedback_entries = await search_service._feedback_db.get_all_feedback_entries()
        except Exception as e:
            logger.error(f"Error getting feedback entries: {e}")
            feedback_entries = []
        
        try:
            ignored_medications = await search_service._feedback_db.get_ignored_medications()
        except Exception as e:
            logger.error(f"Error getting ignored medications: {e}")
            ignored_medications = []
        
        # Convert to the expected format
        feedback_list = []
        for key, data in feedback_counts.items():
            feedback_list.append({
                "drug_name": data["drug_name"],
                "query": data["query"],
                "helpful_count": data["helpful"],
                "not_helpful_count": data["not_helpful"],
                "total_votes": data["helpful"] + data["not_helpful"]
            })
        
        return {
            "success": True,
            "stats": {
                "total_feedback": stats["total_feedback"],
                "positive_ratings": stats["total_helpful"],
                "negative_ratings": stats["total_not_helpful"],
                "recent_feedback_24h": stats["recent_feedback_24h"],
                "helpful_percentage": round(stats["helpful_percentage"], 2),
                "ignored_medications_count": len(ignored_medications),
                "last_updated": datetime.now().isoformat()
            },
            "feedback_list": feedback_list,
            "feedback_entries": feedback_entries,
            "ignored_medications": ignored_medications,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Failed to get feedback stats: {str(e)}")
        return {"success": False, "message": str(e)}

@app.post("/feedback/remove")
async def remove_feedback(request: dict):
    """Remove specific feedback entry."""
    try:
        drug_name = request.get("drug_name")
        query = request.get("query")
        
        if not drug_name or not query:
            return {"success": False, "message": "drug_name and query are required"}
        
        search_service = await get_post_discharge_search_service()
        success = search_service._feedback_db.remove_feedback(drug_name, query)
        
        if success:
            return {"success": True, "message": "Feedback removed successfully"}
        else:
            return {"success": False, "message": "Feedback not found"}
            
    except Exception as e:
        logger.error(f"Error removing feedback: {str(e)}")
        return {"success": False, "message": str(e)}

@app.post("/feedback/unignore")
async def unignore_medication(request: dict):
    """Unignore a medication by removing its negative feedback."""
    try:
        drug_name = request.get("drug_name")
        query = request.get("query")
        
        if not drug_name or not query:
            return {"success": False, "message": "drug_name and query are required"}
        
        search_service = await get_post_discharge_search_service()
        
        # Remove all negative feedback for this drug-query combination
        # This effectively "unignores" the medication
        success = search_service._feedback_db.remove_feedback(drug_name, query)
        
        if success:
            return {"success": True, "message": f"Medication '{drug_name}' unignored successfully for query '{query}'"}
        else:
            return {"success": False, "message": "Failed to unignore medication"}
            
    except Exception as e:
        logger.error(f"Error unignoring medication: {str(e)}")
        return {"success": False, "message": str(e)}

@app.get("/admin/stats")
async def get_admin_stats():
    """Get admin dashboard statistics."""
    try:
        search_service = await get_post_discharge_search_service()
        
        # Get system health
        system_health = await get_system_status()
        
        # Get feedback database stats
        db_stats = search_service._feedback_db.get_database_stats()
        
        return {
            "success": True,
            "system_health": {
                "status": "Online",
                "api_health": "Healthy", 
                "database_status": "Connected"
            },
            "database_stats": db_stats,
            "charts": {
                "search_performance": "placeholder",
                "feedback_trends": "placeholder"
            },
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Failed to get admin stats: {str(e)}")
        return {"success": False, "message": str(e)}

@app.post("/admin/clear-cache")
async def clear_medication_cache():
    """Clear the medication cache."""
    try:
        cache = await get_medication_cache()
        cache.clear_cache()
        
        return {"success": True, "message": "Medication cache cleared successfully"}
        
    except Exception as e:
        logger.error(f"Failed to clear medication cache: {str(e)}")
        return {"success": False, "message": str(e)}

@app.post("/admin/clear-rxlist")
async def clear_rxlist_database():
    """Clear the RxList database."""
    try:
        rxlist_db = await get_rxlist_database()
        rxlist_db.clear_all_drugs()
        
        return {"success": True, "message": "RxList database cleared successfully"}
        
    except Exception as e:
        logger.error(f"Failed to clear RxList database: {str(e)}")
        return {"success": False, "message": str(e)}

@app.post("/feedback/clear")
async def clear_all_feedback():
    """Clear all feedback data."""
    try:
        search_service = await get_post_discharge_search_service()
        success = search_service._feedback_db.clear_all_feedback()
        
        if success:
            return {"success": True, "message": "All feedback cleared successfully"}
        else:
            return {"success": False, "message": "Failed to clear feedback"}
            
    except Exception as e:
        logger.error(f"Error clearing feedback: {str(e)}")
        return {"success": False, "message": str(e)}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    monitor.record_request(success=False)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": time.time()
        }
    )
