#!/usr/bin/env python3
"""
Database Migration Script
Migrates data from SQLite to PostgreSQL or creates initial tables
"""

import os
import sys
import logging
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.database_config import db_config
from app.database_manager import db_manager
from app.database_models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tables():
    """Create all database tables."""
    try:
        logger.info("Creating database tables...")
        db_manager.create_tables()
        logger.info("✅ Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create database tables: {e}")
        return False

def test_connection():
    """Test database connection."""
    try:
        logger.info("Testing database connection...")
        if db_config.test_connection():
            logger.info("✅ Database connection successful")
            return True
        else:
            logger.error("❌ Database connection failed")
            return False
    except Exception as e:
        logger.error(f"❌ Database connection test failed: {e}")
        return False

def migrate_from_sqlite(sqlite_path: str):
    """Migrate data from SQLite to PostgreSQL."""
    if not db_config.is_postgres:
        logger.info("Not using PostgreSQL, skipping migration")
        return True
    
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
            db_manager.add_feedback(
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

def main():
    """Main migration function."""
    logger.info("🚀 Starting database migration...")
    
    # Test connection first
    if not test_connection():
        sys.exit(1)
    
    # Create tables
    if not create_tables():
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
            if not migrate_from_sqlite(sqlite_file):
                logger.warning(f"Failed to migrate {sqlite_file}, continuing...")
    
    logger.info("🎉 Database migration completed successfully!")

if __name__ == "__main__":
    main()
