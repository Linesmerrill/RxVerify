#!/usr/bin/env python3
"""Production startup script for RxVerify application."""

import os
import sys
import uvicorn
from pathlib import Path

# Add the parent directory to the path
sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from app.logging import logger

def main():
    """Start the production server."""
    logger.info("🚀 Starting RxVerify Production Server...")
    
    # Validate environment
    if not settings.OPENAI_API_KEY:
        logger.warning("⚠️  OPENAI_API_KEY not set - LLM responses will use fallback mode")
    
    # Create necessary directories
    os.makedirs("logs", exist_ok=True)
    os.makedirs("chroma_db", exist_ok=True)
    
    logger.info(f"📊 Server Configuration:")
    logger.info(f"  Host: {settings.API_HOST}")
    logger.info(f"  Port: {settings.API_PORT}")
    logger.info(f"  Workers: {settings.API_WORKERS}")
    logger.info(f"  Log Level: {settings.LOG_LEVEL}")
    logger.info(f"  ChromaDB Path: {settings.CHROMADB_PATH}")
    
    # Start server
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        workers=settings.API_WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
        reload=False  # Disable reload in production
    )

if __name__ == "__main__":
    main()
