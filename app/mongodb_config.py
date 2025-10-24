"""
MongoDB Database Configuration Module
Handles MongoDB Atlas connection for persistent storage
"""

import os
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)

class MongoDBConfig:
    """MongoDB configuration manager for Atlas and local development."""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.sync_client: Optional[MongoClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        self.sync_database: Optional[Database] = None
        self.mongodb_url = self._get_mongodb_url()
        self.database_name = self._get_database_name()
        self.is_atlas = 'mongodb+srv://' in self.mongodb_url
        
    def _get_mongodb_url(self) -> str:
        """Get MongoDB URL from environment or default to local."""
        # Check for MongoDB Atlas URI
        if 'MONGODB_URI' in os.environ:
            url = os.environ['MONGODB_URI']
            logger.info("Using MongoDB Atlas from MONGODB_URI")
            return url
        
        # Check for custom MongoDB URL
        if 'MONGODB_URL' in os.environ:
            logger.info("Using MongoDB from MONGODB_URL")
            return os.environ['MONGODB_URL']
        
        # Default to local MongoDB for development
        host = os.environ.get('MONGODB_HOST', 'localhost')
        port = os.environ.get('MONGODB_PORT', '27017')
        logger.info(f"Using local MongoDB at {host}:{port}")
        return f"mongodb://{host}:{port}"
    
    def _get_database_name(self) -> str:
        """Get database name from environment or default."""
        return os.environ.get('MONGODB_DATABASE', 'rxverify')
    
    async def connect(self) -> AsyncIOMotorDatabase:
        """Connect to MongoDB and return database instance."""
        try:
            if not self.client:
                self.client = AsyncIOMotorClient(self.mongodb_url)
                self.database = self.client[self.database_name]
                
                # Test connection
                await self.client.admin.command('ping')
                logger.info("MongoDB connection successful")
            
            return self.database
            
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise
    
    def connect_sync(self) -> Database:
        """Connect to MongoDB synchronously and return database instance."""
        try:
            if not self.sync_client:
                self.sync_client = MongoClient(self.mongodb_url)
                self.sync_database = self.sync_client[self.database_name]
                
                # Test connection
                self.sync_client.admin.command('ping')
                logger.info("MongoDB sync connection successful")
            
            return self.sync_database
            
        except Exception as e:
            logger.error(f"MongoDB sync connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    def disconnect_sync(self):
        """Disconnect from MongoDB synchronously."""
        if self.sync_client:
            self.sync_client.close()
            logger.info("MongoDB sync connection closed")
    
    async def test_connection(self) -> bool:
        """Test MongoDB connection."""
        try:
            db = await self.connect()
            await db.command('ping')
            logger.info("MongoDB connection test successful")
            return True
        except Exception as e:
            logger.error(f"MongoDB connection test failed: {e}")
            return False
    
    def test_connection_sync(self) -> bool:
        """Test MongoDB connection synchronously."""
        try:
            db = self.connect_sync()
            db.command('ping')
            logger.info("MongoDB sync connection test successful")
            return True
        except Exception as e:
            logger.error(f"MongoDB sync connection test failed: {e}")
            return False

# Global MongoDB configuration instance
mongodb_config = MongoDBConfig()
