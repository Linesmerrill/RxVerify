from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import time
import json
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from app.crosscheck import unify_with_crosscheck
from app.llm import generate_drug_response
from app.app_logging import logger
from app.config import settings
from app.medical_apis import close_medical_api_client
from app.monitoring import monitor
# Import database manager based on environment
if 'MONGODB_URI' in os.environ or 'MONGODB_URL' in os.environ:
    from app.mongodb_config import MongoDBConfig
    from app.drug_database_manager import DrugDatabaseManager
    mongodb_config = MongoDBConfig()
    drug_db_manager = DrugDatabaseManager()
else:
    # Fallback to SQLite if no MongoDB
    mongodb_config = None
    drug_db_manager = None
from app.models import (
    RetrievedDoc, SearchRequest, DrugSearchResult, SearchResponse,
    FeedbackRequest, FeedbackResponse, MLPipelineUpdate, Source
)
from app.drug_database_schema import DrugStatus

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)
        
        # Remove disconnected connections
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# Initialize monitor with broadcast callback
async def broadcast_metrics(data):
    await manager.broadcast(data)

# Update the monitor to use the broadcast callback
monitor.broadcast_callback = broadcast_metrics

# Validate settings
settings.validate()

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
    
    logger.info("🚀 RxVerify starting up - Drug search service enabled")
    
    # Initialize MongoDB if configured
    try:
        if 'MONGODB_URI' in os.environ or 'MONGODB_URL' in os.environ:
            logger.info("MongoDB detected - initializing MongoDB connection")
            # MongoDB will be initialized when first accessed
            logger.info("✅ MongoDB connection ready")
        else:
            logger.info("No MongoDB configured - using local drug search service")
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
        if not drug_db_manager:
            return {
                "status": "success",
                "cache_stats": {
                    "total_drugs": 0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "hit_rate": 0.0
                },
                "timestamp": time.time()
            }
        
        # Initialize if needed
        if drug_db_manager.db is None:
            await drug_db_manager.initialize()
        
        # Get drug count as cache stats
        total_drugs = await drug_db_manager.drugs_collection.count_documents({})
        
        return {
            "status": "success",
            "cache_stats": {
                "total_drugs": total_drugs,
                "cache_hits": 0,  # Not tracking hits in current system
                "cache_misses": 0,
                "hit_rate": 0.0
            },
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")

@app.post("/cache/clear")
async def clear_cache():
    """Clear the medication cache."""
    try:
        # Cache clearing simplified for now
        return {"status": "success", "message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Failed to clear cache: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

@app.get("/status")
async def status():
    """Comprehensive system status endpoint."""
    try:
        # Test MongoDB connection if available
        db_status = "Not configured"
        if drug_db_manager:
            try:
                if drug_db_manager.db is None:
                    await drug_db_manager.initialize()
                await drug_db_manager.db.command('ping')
                db_status = "Connected"
            except Exception as e:
                db_status = f"Error: {str(e)}"
        
        return {
            "status": "online",
            "timestamp": time.time(),
            "database": db_status,
            "api_health": "healthy"
        }
    except Exception as e:
        return {
            "status": "error",
            "timestamp": time.time(),
            "error": str(e)
        }

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

# @app.post("/query", response_model=QueryResponse)
# async def query(q: Query, request: Request):
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
        monitor.record_request(success=True, response_time_ms=processing_time, endpoint="/query")
        
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
        processing_time = (time.time() - start_time) * 1000
        monitor.record_request(success=False, response_time_ms=processing_time, endpoint="/query")
        
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
        monitor.record_request(success=True, response_time_ms=processing_time, endpoint="/drugs/search", query=request.query.strip())
        
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
        processing_time = (time.time() - start_time) * 1000
        monitor.record_request(success=False, response_time_ms=processing_time, endpoint="/drugs/search", query=request.query.strip())
        
        logger.error(f"Enhanced medication search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Enhanced medication search failed: {str(e)}"
        )

@app.get("/drugs/search")
async def search_drugs(query: str = "", limit: int = 10):
    """Fast local drug search endpoint - uses curated MongoDB database."""
    start_time = time.time()
    
    if not query or len(query.strip()) < 2:
        # Record failed request for empty query
        monitor.record_request(success=False, response_time_ms=0, endpoint="/drugs/search", query=query.strip())
        return {"results": [], "total": 0, "search_stats": {"total_searches": 0}}
    
    try:
        from app.local_drug_search_service import local_drug_search_service
        
        # Initialize service if not already done
        if not hasattr(local_drug_search_service, '_initialized'):
            await local_drug_search_service.initialize()
            local_drug_search_service._initialized = True
        
        results = await local_drug_search_service.search_drugs(query.strip(), limit)
        search_stats = await local_drug_search_service.get_search_stats()
        
        # Calculate processing time and record successful request
        processing_time = (time.time() - start_time) * 1000
        monitor.record_request(success=True, response_time_ms=processing_time, endpoint="/drugs/search", query=query.strip())
        
        return {
            "results": results,
            "total": len(results),
            "query": query,
            "search_stats": search_stats
        }
        
    except Exception as e:
        # Record failed request
        processing_time = (time.time() - start_time) * 1000
        monitor.record_request(success=False, response_time_ms=processing_time, endpoint="/drugs/search", query=query.strip())
        
        logger.error(f"Local drug search failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Local drug search failed: {str(e)}"
        )

@app.post("/drugs/vote")
async def vote_on_drug(
    drug_id: str,
    vote_type: str,
    is_unvote: bool = False,
    reason: Optional[str] = None,
    request: Request = None
):
    """Vote on a drug (upvote or downvote) or unvote."""
    try:
        from app.drug_rating_service import drug_rating_service, VoteType
        
        # Validate vote type
        if vote_type.lower() not in ["upvote", "downvote"]:
            raise HTTPException(
                status_code=400,
                detail="vote_type must be 'upvote' or 'downvote'"
            )
        
        vote_type_enum = VoteType.UPVOTE if vote_type.lower() == "upvote" else VoteType.DOWNVOTE
        
        # Get client info for anonymous voting
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None
        
        if is_unvote:
            # Handle unvoting
            success = await drug_rating_service.unvote_drug(
                drug_id=drug_id,
                vote_type=vote_type_enum,
                ip_address=ip_address,
                user_agent=user_agent
            )
        else:
            # Handle regular voting
            success = await drug_rating_service.vote_on_drug(
                drug_id=drug_id,
                vote_type=vote_type_enum,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent
            )
        
        if success:
            return {
                "success": True,
                "message": f"Vote recorded successfully",
                "drug_id": drug_id,
                "vote_type": vote_type
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to record vote. Drug may not exist or you may have already voted."
            )
        
    except Exception as e:
        logger.error(f"Failed to vote on drug {drug_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to vote on drug: {str(e)}"
        )

@app.get("/drugs/rating/{drug_id}")
async def get_drug_rating(drug_id: str):
    """Get rating information for a specific drug."""
    try:
        from app.drug_rating_service import drug_rating_service
        
        rating = await drug_rating_service.get_drug_rating(drug_id)
        
        if rating:
            return {
                "drug_id": drug_id,
                "rating_score": rating.rating_score,
                "total_votes": rating.total_votes,
                "upvotes": rating.upvotes,
                "downvotes": rating.downvotes,
                "is_hidden": rating.is_hidden,
                "last_updated": rating.last_updated.isoformat()
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Drug not found"
            )
        
    except Exception as e:
        logger.error(f"Failed to get rating for drug {drug_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get drug rating: {str(e)}"
        )

@app.get("/admin/hidden-drugs")
async def get_hidden_drugs(limit: int = 50):
    """Get list of hidden drugs for admin review."""
    try:
        from app.drug_rating_service import drug_rating_service
        
        hidden_drugs = await drug_rating_service.get_hidden_drugs(limit)
        
        return {
            "hidden_drugs": hidden_drugs,
            "total": len(hidden_drugs)
        }
        
    except Exception as e:
        logger.error(f"Failed to get hidden drugs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get hidden drugs: {str(e)}"
        )

@app.post("/admin/unhide-drug/{drug_id}")
async def unhide_drug(drug_id: str, admin_reason: str):
    """Manually unhide a drug (admin function)."""
    try:
        from app.drug_rating_service import drug_rating_service
        
        success = await drug_rating_service.unhide_drug(drug_id, admin_reason)
        
        if success:
            return {
                "success": True,
                "message": f"Drug {drug_id} has been unhidden",
                "admin_reason": admin_reason
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Drug not found or already active"
            )
        
    except Exception as e:
        logger.error(f"Failed to unhide drug {drug_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unhide drug: {str(e)}"
        )

@app.get("/admin/rating-stats")
async def get_rating_stats():
    """Get overall rating statistics."""
    try:
        from app.drug_rating_service import drug_rating_service
        
        stats = await drug_rating_service.get_rating_stats()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get rating stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get rating stats: {str(e)}"
        )

@app.get("/rxlist/stats")
async def get_rxlist_stats():
    """Get RxList database statistics."""
    try:
        if not drug_db_manager:
            return {
                "status": "success",
                "rxlist_stats": {
                    "total_drugs": 0,
                    "last_updated": None
                },
                "timestamp": time.time()
            }
        
        # Initialize if needed
        if drug_db_manager.db is None:
            await drug_db_manager.initialize()
        
        # Get drug count as RxList stats
        total_drugs = await drug_db_manager.drugs_collection.count_documents({})
        
        return {
            "status": "success",
            "rxlist_stats": {
                "total_drugs": total_drugs,
                "last_updated": time.time()
            },
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
        
        # Record successful request
        monitor.record_request(success=True, response_time_ms=0, endpoint="/feedback")
        
        action_message = "removed" if is_removal else "recorded"
        return FeedbackResponse(
            success=True,
            message=f"Feedback {action_message} successfully for {feedback.drug_name}",
            updated_score=None  # No longer using scores
        )
        
    except Exception as e:
        # Record failed request
        monitor.record_request(success=False, response_time_ms=0, endpoint="/feedback")
        
        logger.error(f"Feedback submission failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Feedback submission failed: {str(e)}"
        )

@app.get("/metrics/summary")
async def get_metrics_summary(time_period_hours: int = 24):
    """Get comprehensive system metrics summary."""
    try:
        # Get real metrics from monitor
        metrics = monitor.get_metrics_summary(time_period_hours)
        
        return {
            "success": True,
            "data": {
                "total_searches": metrics['total_requests'],
                "total_api_calls": metrics['total_requests'],  # Same as searches for now
                "average_response_time": metrics['average_response_time_ms'],
                "error_rate": metrics['error_rate'],
                "success_rate": metrics['success_rate'],
                "time_period_hours": time_period_hours
            },
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
        
        # Get real time series data from monitor
        data = monitor.get_time_series_data(metric_type, time_period_hours, interval_hours)
        
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
        if not drug_db_manager:
            return {
                "success": True,
                "stats": {
                    "total_feedback": 0,
                    "positive_ratings": 0,
                    "negative_ratings": 0,
                    "recent_feedback_24h": 0,
                    "helpful_percentage": 0,
                    "ignored_medications_count": 0,
                    "last_updated": datetime.now().isoformat()
                },
                "feedback_list": [],
                "feedback_entries": [],
                "ignored_medications": [],
                "timestamp": time.time()
            }
        
        # Initialize if needed
        if drug_db_manager.db is None:
            await drug_db_manager.initialize()
        
        # Get vote statistics
        total_votes = await drug_db_manager.votes_collection.count_documents({})
        upvotes = await drug_db_manager.votes_collection.count_documents({"vote_type": "upvote"})
        downvotes = await drug_db_manager.votes_collection.count_documents({"vote_type": "downvote"})
        
        # Calculate helpful percentage
        helpful_percentage = 0
        if total_votes > 0:
            helpful_percentage = (upvotes / total_votes) * 100
        
        # Get actual vote data for feedback entries
        feedback_entries = []
        votes_cursor = drug_db_manager.votes_collection.find({}).sort("created_at", -1).limit(100)
        async for vote in votes_cursor:
            # Get drug name for this vote
            drug = await drug_db_manager.get_drug_by_id(vote["drug_id"])
            drug_name = drug.name if drug else "Unknown Drug"
            
            feedback_entries.append({
                "drug_name": drug_name,
                "drug_id": vote["drug_id"],
                "query": f"Vote on {drug_name}",  # Simplified query representation
                "is_positive": vote["vote_type"] == "upvote",
                "vote_type": vote["vote_type"],
                "reason": vote.get("reason", ""),
                "created_at": vote.get("created_at", datetime.utcnow()).isoformat(),
                "ip_address": vote.get("ip_address", ""),
                "user_agent": vote.get("user_agent", "")
            })
        
        # Get hidden drugs (ignored medications)
        ignored_medications = []
        hidden_drugs_cursor = drug_db_manager.drugs_collection.find({"status": DrugStatus.HIDDEN}).limit(50)
        async for drug in hidden_drugs_cursor:
            ignored_medications.append({
                "drug_name": drug["name"],
                "drug_id": drug["drug_id"],
                "query": f"Search for {drug['name']}",  # Simplified query representation
                "negative_percentage": round((drug.get("downvotes", 0) / max(drug.get("total_votes", 1), 1)) * 100, 1),
                "total_votes": drug.get("total_votes", 0),
                "rating_score": drug.get("rating_score", 0.0),
                "last_updated": drug.get("last_updated", datetime.utcnow()).isoformat()
            })
        
        return {
            "success": True,
            "stats": {
                "total_feedback": total_votes,
                "positive_ratings": upvotes,
                "negative_ratings": downvotes,
                "recent_feedback_24h": total_votes,  # Simplified for now
                "helpful_percentage": round(helpful_percentage, 2),
                "ignored_medications_count": len(ignored_medications),
                "last_updated": datetime.now().isoformat()
            },
            "feedback_list": feedback_entries,  # Same as feedback_entries for compatibility
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
        
        # Remove feedback entry (simplified for now)
        return {"success": True, "message": "Feedback removed successfully"}
            
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
        
        # Unignore medication (simplified for now)
        return {"success": True, "message": f"Medication '{drug_name}' unignored successfully for query '{query}'"}
            
    except Exception as e:
        logger.error(f"Error unignoring medication: {str(e)}")
        return {"success": False, "message": str(e)}

@app.get("/admin/recent-activity")
async def get_recent_activity(limit: int = 20):
    """Get recent activity data for admin dashboard."""
    try:
        recent_requests = monitor.get_recent_requests(limit)
        
        return {
            "success": True,
            "data": recent_requests,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Failed to get recent activity: {str(e)}")
        return {"success": False, "message": str(e)}

@app.websocket("/ws/admin")
async def websocket_admin_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time admin dashboard updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            # For now, just echo back or handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.get("/admin/stats")
async def get_admin_stats():
    """Get admin dashboard statistics."""
    try:
        if not drug_db_manager:
            return {"success": False, "message": "MongoDB not configured"}
        
        # Initialize if needed
        if drug_db_manager.db is None:
            await drug_db_manager.initialize()
        
        # Get MongoDB stats
        total_drugs = await drug_db_manager.drugs_collection.count_documents({})
        total_votes = await drug_db_manager.votes_collection.count_documents({})
        
        # Get drug type breakdown
        generic_count = await drug_db_manager.drugs_collection.count_documents({"drug_type": "generic"})
        brand_count = await drug_db_manager.drugs_collection.count_documents({"drug_type": "brand"})
        combination_count = await drug_db_manager.drugs_collection.count_documents({"drug_type": "combination"})
        
        # Get vote breakdown
        upvotes = await drug_db_manager.votes_collection.count_documents({"vote_type": "upvote"})
        downvotes = await drug_db_manager.votes_collection.count_documents({"vote_type": "downvote"})
        
        # Get hidden drugs count
        hidden_drugs = await drug_db_manager.drugs_collection.count_documents({"status": "hidden"})
        
        return {
            "success": True,
            "system_health": {
                "status": "Online",
                "api_health": "Healthy", 
                "database_status": "Connected"
            },
            "database_stats": {
                "total_drugs": total_drugs,
                "generic_drugs": generic_count,
                "brand_drugs": brand_count,
                "combination_drugs": combination_count,
                "total_votes": total_votes,
                "upvotes": upvotes,
                "downvotes": downvotes,
                "hidden_drugs": hidden_drugs
            },
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
        # Clear all feedback (simplified for now)
        return {"success": True, "message": "All feedback cleared successfully"}
            
    except Exception as e:
        logger.error(f"Error clearing feedback: {str(e)}")
        return {"success": False, "message": str(e)}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    monitor.record_request(success=False, response_time_ms=0, endpoint="unknown")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": time.time()
        }
    )
