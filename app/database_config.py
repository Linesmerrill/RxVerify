"""
Database Configuration Module
Handles both SQLite (local) and PostgreSQL (production) database connections
"""

import os
import logging
from typing import Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration manager for SQLite and PostgreSQL."""
    
    def __init__(self):
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.database_url = self._get_database_url()
        self.is_postgres = self.database_url.startswith('postgresql://')
        
    def _get_database_url(self) -> str:
        """Get database URL from environment or default to SQLite."""
        # Check for Heroku PostgreSQL DATABASE_URL
        if 'DATABASE_URL' in os.environ:
            url = os.environ['DATABASE_URL']
            # Heroku provides postgres:// but SQLAlchemy needs postgresql://
            if url.startswith('postgres://'):
                url = url.replace('postgres://', 'postgresql://', 1)
            logger.info("Using PostgreSQL database from DATABASE_URL")
            return url
        
        # Check for custom PostgreSQL URL
        if 'POSTGRES_URL' in os.environ:
            logger.info("Using PostgreSQL database from POSTGRES_URL")
            return os.environ['POSTGRES_URL']
        
        # Default to SQLite for local development
        db_path = os.environ.get('SQLITE_DB_PATH', 'rxverify.db')
        logger.info(f"Using SQLite database at {db_path}")
        return f"sqlite:///{db_path}"
    
    def create_engine(self) -> Engine:
        """Create SQLAlchemy engine based on database type."""
        if self.is_postgres:
            # PostgreSQL configuration
            self.engine = create_engine(
                self.database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False  # Set to True for SQL query logging
            )
        else:
            # SQLite configuration
            self.engine = create_engine(
                self.database_url,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
                echo=False  # Set to True for SQL query logging
            )
        
        return self.engine
    
    def get_session_local(self):
        """Get session factory for database operations."""
        if not self.engine:
            self.create_engine()
        
        if not self.SessionLocal:
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
        
        return self.SessionLocal
    
    def get_db_session(self):
        """Get database session for dependency injection."""
        SessionLocal = self.get_session_local()
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            if not self.engine:
                self.create_engine()
            
            with self.engine.connect() as conn:
                conn.execute("SELECT 1")
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

# Global database configuration instance
db_config = DatabaseConfig()
