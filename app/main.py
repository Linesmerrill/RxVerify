from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import time
from app.retriever import retrieve
from app.crosscheck import unify_with_crosscheck
from app.llm import generate_drug_response
from app.monitoring import monitor, get_system_status
from app.logging import logger
from app.config import settings
from app.medical_apis import close_medical_api_client
from app.search_service import get_search_service
from app.medication_cache import get_medication_cache

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

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    logger.info("🚀 RxVerify starting up - Real-time medical database integration enabled")

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

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class SearchResponse(BaseModel):
    results: list
    total_found: int
    processing_time_ms: float

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
    """Fast medication search endpoint for autocomplete functionality."""
    start_time = time.time()
    
    try:
        logger.info(f"Processing medication search: {request.query[:50]}...")
        
        # Get search service
        search_service = await get_search_service()
        
        # Perform search
        results = await search_service.search_medications(request.query, request.limit)
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Record successful request
        monitor.record_request(success=True)
        
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
                "source": result.source
            })
        
        return SearchResponse(
            results=results_dict,
            total_found=len(results),
            processing_time_ms=round(processing_time, 2)
        )
        
    except Exception as e:
        # Record failed request
        monitor.record_request(success=False)
        
        logger.error(f"Medication search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Medication search failed: {str(e)}"
        )

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
