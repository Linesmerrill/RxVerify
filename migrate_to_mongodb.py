#!/usr/bin/env python3
"""
MongoDB Migration Script
Migrates data from SQLite to MongoDB Atlas or creates initial collections
"""

import os
import sys
import logging
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.mongodb_config import mongodb_config
from app.mongodb_manager import mongodb_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_collections():
    """Create MongoDB collections and indexes."""
    try:
        logger.info("Creating MongoDB collections and indexes...")
        await mongodb_manager.create_indexes()
        logger.info("✅ MongoDB collections and indexes created successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create MongoDB collections: {e}")
        return False

async def test_connection():
    """Test MongoDB connection."""
    try:
        logger.info("Testing MongoDB connection...")
        if await mongodb_config.test_connection():
            logger.info("✅ MongoDB connection successful")
            return True
        else:
            logger.error("❌ MongoDB connection failed")
            return False
    except Exception as e:
        logger.error(f"❌ MongoDB connection test failed: {e}")
        return False

async def migrate_from_sqlite(sqlite_path: str):
    """Migrate data from SQLite to MongoDB."""
    try:
        import sqlite3
        logger.info(f"Migrating data from SQLite database: {sqlite_path}")
        
        # Connect to SQLite database
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        # Migrate feedback data
        logger.info("Migrating feedback data...")
        sqlite_cursor.execute("SELECT drug_name, query, is_positive, timestamp, user_id, session_id FROM feedback")
        feedback_rows = sqlite_cursor.fetchall()
        
        for row in feedback_rows:
            await mongodb_manager.add_feedback(
                drug_name=row[0],
                query=row[1],
                is_positive=bool(row[2]),
                user_id=row[4],
                session_id=row[5]
            )
        
        logger.info(f"✅ Migrated {len(feedback_rows)} feedback entries")
        
        # Close SQLite connection
        sqlite_conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

async def main():
    """Main migration function."""
    logger.info("🚀 Starting MongoDB migration...")
    
    # Test connection first
    if not await test_connection():
        sys.exit(1)
    
    # Create collections and indexes
    if not await create_collections():
        sys.exit(1)
    
    # Check if we should migrate from SQLite
    sqlite_files = [
        "feedback_database.db",
        "metrics_database.db", 
        "medication_cache.db",
        "rxlist_database.db"
    ]
    
    for sqlite_file in sqlite_files:
        if os.path.exists(sqlite_file):
            logger.info(f"Found SQLite file: {sqlite_file}")
            if not await migrate_from_sqlite(sqlite_file):
                logger.warning(f"Failed to migrate {sqlite_file}, continuing...")
    
    logger.info("🎉 MongoDB migration completed successfully!")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
