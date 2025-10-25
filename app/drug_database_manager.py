"""
MongoDB Manager for Curated Drug Database

This module handles all MongoDB operations for our curated drug database,
including CRUD operations, search functionality, and database management.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import IndexModel, ASCENDING, TEXT, DESCENDING
from app.drug_database_schema import DrugEntry, DrugSearchResult, DrugType, DrugStatus, DrugDatabaseStats
from app.mongodb_config import MongoDBConfig

logger = logging.getLogger(__name__)


class DrugDatabaseManager:
    """Manages the curated drug database in MongoDB."""
    
    def __init__(self):
        self.mongodb_config = MongoDBConfig()
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.drugs_collection: Optional[AsyncIOMotorCollection] = None
        self.stats_collection: Optional[AsyncIOMotorCollection] = None
        self.votes_collection: Optional[AsyncIOMotorCollection] = None
    
    async def initialize(self):
        """Initialize MongoDB connection and collections."""
        try:
            self.db = await self.mongodb_config.connect()
            self.client = self.mongodb_config.client
            self.drugs_collection = self.db.drugs
            self.stats_collection = self.db.drug_stats
            self.votes_collection = self.db.drug_votes
            
            # Create indexes for fast searching
            await self._create_indexes()
            
            logger.info("Drug database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize drug database manager: {str(e)}")
            raise
    
    async def _create_indexes(self):
        """Create MongoDB indexes for optimal search performance."""
        try:
            # Text search index for drug names and search terms
            text_index = IndexModel([
                ("name", TEXT),
                ("search_terms", TEXT),
                ("generic_name", TEXT),
                ("brand_names", TEXT),
                ("drug_class", TEXT)
            ], name="drug_text_search")
            
            # Compound indexes for different search patterns
            compound_indexes = [
                IndexModel([("drug_type", ASCENDING), ("status", ASCENDING)]),
                IndexModel([("generic_drug_id", ASCENDING)]),
                IndexModel([("combination_drug_ids", ASCENDING)]),
                IndexModel([("rxnorm_id", ASCENDING)]),
                IndexModel([("primary_search_term", ASCENDING)]),
                IndexModel([("last_updated", DESCENDING)]),
                IndexModel([("search_count", DESCENDING)])
            ]
            
            await self.drugs_collection.create_indexes([text_index] + compound_indexes)
            logger.info("Drug database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create drug database indexes: {str(e)}")
            raise
    
    async def insert_drug(self, drug: DrugEntry) -> bool:
        """Insert a single drug entry."""
        try:
            result = await self.drugs_collection.insert_one(drug.dict())
            logger.debug(f"Inserted drug: {drug.name} ({drug.drug_id})")
            return result.inserted_id is not None
            
        except Exception as e:
            logger.error(f"Failed to insert drug {drug.name}: {str(e)}")
            return False
    
    async def insert_drugs_batch(self, drugs: List[DrugEntry]) -> int:
        """Insert multiple drug entries in batch."""
        try:
            if not drugs:
                return 0
            
            drug_docs = [drug.dict() for drug in drugs]
            result = await self.drugs_collection.insert_many(drug_docs)
            
            logger.info(f"Inserted {len(result.inserted_ids)} drugs in batch")
            return len(result.inserted_ids)
            
        except Exception as e:
            logger.error(f"Failed to insert drugs batch: {str(e)}")
            return 0
    
    async def update_drug(self, drug_id: str, updates: Dict[str, Any]) -> bool:
        """Update a drug entry."""
        try:
            updates["last_updated"] = datetime.utcnow()
            result = await self.drugs_collection.update_one(
                {"drug_id": drug_id},
                {"$set": updates}
            )
            
            if result.modified_count > 0:
                logger.debug(f"Updated drug: {drug_id}")
                return True
            else:
                logger.warning(f"No drug found to update: {drug_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update drug {drug_id}: {str(e)}")
            return False
    
    async def delete_drug(self, drug_id: str) -> bool:
        """Delete a drug entry."""
        try:
            result = await self.drugs_collection.delete_one({"drug_id": drug_id})
            
            if result.deleted_count > 0:
                logger.info(f"Deleted drug: {drug_id}")
                return True
            else:
                logger.warning(f"No drug found to delete: {drug_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete drug {drug_id}: {str(e)}")
            return False
    
    async def get_drug_by_id(self, drug_id: str) -> Optional[DrugEntry]:
        """Get a drug by its ID."""
        try:
            doc = await self.drugs_collection.find_one({"drug_id": drug_id})
            if doc:
                return DrugEntry(**doc)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get drug {drug_id}: {str(e)}")
            return None
    
    async def search_drugs(self, query: str, limit: int = 10) -> List[DrugSearchResult]:
        """
        Smart drug search with intelligent query interpretation.
        
        Search logic:
        - Generic name search: Show only generic drug
        - Brand name search: Show generic + brand info
        - Combination search: Show combo drugs
        - Partial matches: Show relevant drugs
        """
        try:
            query_lower = query.lower().strip()
            
            # Determine search strategy based on query
            search_strategy = self._determine_search_strategy(query_lower)
            
            # Execute search based on strategy
            if search_strategy == "generic_only":
                results = await self._search_generic_only(query_lower, limit)
            elif search_strategy == "brand_search":
                results = await self._search_brand(query_lower, limit)
            elif search_strategy == "combination_search":
                results = await self._search_combination(query_lower, limit)
            else:
                results = await self._search_general(query_lower, limit)
            
            # Update search statistics
            await self._update_search_stats(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search drugs for '{query}': {str(e)}")
            return []
    
    def _determine_search_strategy(self, query: str) -> str:
        """Determine the best search strategy based on query content."""
        
        # Check for combination indicators
        if any(word in query for word in ["and", "with", "plus", "+", "-"]):
            return "combination_search"
        
        # Check if query looks like a brand name (capitalized, specific)
        if query.isupper() or (query[0].isupper() and len(query) > 3):
            return "brand_search"
        
        # Check if query looks like a generic name (lowercase, common)
        if query.islower() and len(query) > 3:
            return "generic_only"
        
        return "general"
    
    async def _search_generic_only(self, query: str, limit: int) -> List[DrugSearchResult]:
        """Search for generic drugs only."""
        pipeline = [
            {
                "$match": {
                    "drug_type": DrugType.GENERIC,
                    "status": {"$ne": DrugStatus.HIDDEN},  # Exclude hidden drugs
                    "$or": [
                        {"name": {"$regex": query, "$options": "i"}},
                        {"search_terms": {"$regex": query, "$options": "i"}},
                        {"primary_search_term": {"$regex": query, "$options": "i"}}
                    ]
                }
            },
            {
                "$addFields": {
                    "relevance_score": {
                        "$cond": [
                            {"$eq": ["$primary_search_term", query]}, 100,
                            {"$cond": [
                                {"$eq": ["$name", {"$toLower": "$name"}]}, 90,
                                80
                            ]}
                        ]
                    }
                }
            },
            {"$sort": {"relevance_score": -1, "search_count": -1}},
            {"$limit": limit}
        ]
        
        cursor = self.drugs_collection.aggregate(pipeline)
        results = []
        
        async for doc in cursor:
            results.append(DrugSearchResult(
                drug_id=doc["drug_id"],
                name=doc["name"],
                drug_type=doc["drug_type"],
                generic_name=doc.get("generic_name"),
                brand_names=doc.get("brand_names", []),
                drug_class=doc.get("drug_class"),
                common_uses=doc.get("common_uses", []),
                manufacturer=doc.get("manufacturer"),
                rxnorm_id=doc.get("rxnorm_id"),
                relevance_score=doc["relevance_score"],
                match_type="generic",
                rating_score=doc.get("rating_score", 0.0),
                total_votes=doc.get("total_votes", 0),
                upvotes=doc.get("upvotes", 0),
                downvotes=doc.get("downvotes", 0),
                is_hidden=doc.get("status") == DrugStatus.HIDDEN
            ))
        
        return results
    
    async def _search_brand(self, query: str, limit: int) -> List[DrugSearchResult]:
        """Search for brand names and show generic info."""
        pipeline = [
            {
                "$match": {
                    "status": {"$ne": DrugStatus.HIDDEN},  # Exclude hidden drugs
                    "$or": [
                        {"brand_names": {"$regex": query, "$options": "i"}},
                        {"name": {"$regex": query, "$options": "i"}},
                        {"search_terms": {"$regex": query, "$options": "i"}}
                    ]
                }
            },
            {
                "$addFields": {
                    "relevance_score": {
                        "$cond": [
                            {"$in": [query, {"$map": {"input": "$brand_names", "as": "brand", "in": {"$toLower": "$$brand"}}}]}, 100,
                            {"$cond": [
                                {"$eq": ["$name", {"$toLower": "$name"}]}, 90,
                                80
                            ]}
                        ]
                    }
                }
            },
            {"$sort": {"relevance_score": -1, "search_count": -1}},
            {"$limit": limit}
        ]
        
        cursor = self.drugs_collection.aggregate(pipeline)
        results = []
        
        async for doc in cursor:
            results.append(DrugSearchResult(
                drug_id=doc["drug_id"],
                name=doc["name"],
                drug_type=doc["drug_type"],
                generic_name=doc.get("generic_name"),
                brand_names=doc.get("brand_names", []),
                drug_class=doc.get("drug_class"),
                common_uses=doc.get("common_uses", []),
                manufacturer=doc.get("manufacturer"),
                rxnorm_id=doc.get("rxnorm_id"),
                relevance_score=doc["relevance_score"],
                match_type="brand",
                rating_score=doc.get("rating_score", 0.0),
                total_votes=doc.get("total_votes", 0),
                upvotes=doc.get("upvotes", 0),
                downvotes=doc.get("downvotes", 0),
                is_hidden=doc.get("status") == DrugStatus.HIDDEN
            ))
        
        return results
    
    async def _search_combination(self, query: str, limit: int) -> List[DrugSearchResult]:
        """Search for combination drugs."""
        pipeline = [
            {
                "$match": {
                    "drug_type": DrugType.COMBINATION,
                    "status": {"$ne": DrugStatus.HIDDEN},  # Exclude hidden drugs
                    "$or": [
                        {"name": {"$regex": query, "$options": "i"}},
                        {"search_terms": {"$regex": query, "$options": "i"}},
                        {"active_ingredients": {"$regex": query, "$options": "i"}}
                    ]
                }
            },
            {
                "$addFields": {
                    "relevance_score": {
                        "$cond": [
                            {"$eq": ["$primary_search_term", query]}, 100,
                            80
                        ]
                    }
                }
            },
            {"$sort": {"relevance_score": -1, "search_count": -1}},
            {"$limit": limit}
        ]
        
        cursor = self.drugs_collection.aggregate(pipeline)
        results = []
        
        async for doc in cursor:
            results.append(DrugSearchResult(
                drug_id=doc["drug_id"],
                name=doc["name"],
                drug_type=doc["drug_type"],
                generic_name=doc.get("generic_name"),
                brand_names=doc.get("brand_names", []),
                drug_class=doc.get("drug_class"),
                common_uses=doc.get("common_uses", []),
                manufacturer=doc.get("manufacturer"),
                rxnorm_id=doc.get("rxnorm_id"),
                relevance_score=doc["relevance_score"],
                match_type="combination",
                rating_score=doc.get("rating_score", 0.0),
                total_votes=doc.get("total_votes", 0),
                upvotes=doc.get("upvotes", 0),
                downvotes=doc.get("downvotes", 0),
                is_hidden=doc.get("status") == DrugStatus.HIDDEN
            ))
        
        return results
    
    async def _search_general(self, query: str, limit: int) -> List[DrugSearchResult]:
        """General search across all drug types."""
        pipeline = [
            {
                "$match": {
                    "status": {"$ne": DrugStatus.HIDDEN},  # Exclude hidden drugs
                    "$or": [
                        {"name": {"$regex": query, "$options": "i"}},
                        {"search_terms": {"$regex": query, "$options": "i"}},
                        {"drug_class": {"$regex": query, "$options": "i"}},
                        {"common_uses": {"$regex": query, "$options": "i"}}
                    ]
                }
            },
            {
                "$addFields": {
                    "relevance_score": {
                        "$cond": [
                            {"$eq": ["$primary_search_term", query]}, 100,
                            {"$cond": [
                                {"$eq": ["$name", {"$toLower": "$name"}]}, 90,
                                70
                            ]}
                        ]
                    }
                }
            },
            {"$sort": {"relevance_score": -1, "search_count": -1}},
            {"$limit": limit}
        ]
        
        cursor = self.drugs_collection.aggregate(pipeline)
        results = []
        
        async for doc in cursor:
            results.append(DrugSearchResult(
                drug_id=doc["drug_id"],
                name=doc["name"],
                drug_type=doc["drug_type"],
                generic_name=doc.get("generic_name"),
                brand_names=doc.get("brand_names", []),
                drug_class=doc.get("drug_class"),
                common_uses=doc.get("common_uses", []),
                manufacturer=doc.get("manufacturer"),
                rxnorm_id=doc.get("rxnorm_id"),
                relevance_score=doc["relevance_score"],
                match_type="general",
                rating_score=doc.get("rating_score", 0.0),
                total_votes=doc.get("total_votes", 0),
                upvotes=doc.get("upvotes", 0),
                downvotes=doc.get("downvotes", 0),
                is_hidden=doc.get("status") == DrugStatus.HIDDEN
            ))
        
        return results
    
    async def _update_search_stats(self, results: List[DrugSearchResult]):
        """Update search statistics for found drugs."""
        try:
            for result in results:
                await self.drugs_collection.update_one(
                    {"drug_id": result.drug_id},
                    {
                        "$inc": {"search_count": 1},
                        "$set": {"last_searched": datetime.utcnow()}
                    }
                )
        except Exception as e:
            logger.error(f"Failed to update search stats: {str(e)}")
    
    async def get_database_stats(self) -> DrugDatabaseStats:
        """Get statistics about the drug database."""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_drugs": {"$sum": 1},
                        "generic_drugs": {"$sum": {"$cond": [{"$eq": ["$drug_type", DrugType.GENERIC]}, 1, 0]}},
                        "brand_drugs": {"$sum": {"$cond": [{"$eq": ["$drug_type", DrugType.BRAND]}, 1, 0]}},
                        "combination_drugs": {"$sum": {"$cond": [{"$eq": ["$drug_type", DrugType.COMBINATION]}, 1, 0]}},
                        "active_drugs": {"$sum": {"$cond": [{"$eq": ["$status", DrugStatus.ACTIVE]}, 1, 0]}},
                        "discontinued_drugs": {"$sum": {"$cond": [{"$eq": ["$status", DrugStatus.DISCONTINUED]}, 1, 0]}},
                        "last_updated": {"$max": "$last_updated"},
                        "data_sources": {"$addToSet": "$data_source"}
                    }
                }
            ]
            
            cursor = self.drugs_collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            
            if result:
                stats = result[0]
                return DrugDatabaseStats(
                    total_drugs=stats["total_drugs"],
                    generic_drugs=stats["generic_drugs"],
                    brand_drugs=stats["brand_drugs"],
                    combination_drugs=stats["combination_drugs"],
                    active_drugs=stats["active_drugs"],
                    discontinued_drugs=stats["discontinued_drugs"],
                    last_updated=stats["last_updated"],
                    data_sources=stats["data_sources"]
                )
            else:
                return DrugDatabaseStats(
                    total_drugs=0,
                    generic_drugs=0,
                    brand_drugs=0,
                    combination_drugs=0,
                    active_drugs=0,
                    discontinued_drugs=0,
                    last_updated=datetime.utcnow(),
                    data_sources=[]
                )
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {str(e)}")
            return DrugDatabaseStats(
                total_drugs=0,
                generic_drugs=0,
                brand_drugs=0,
                combination_drugs=0,
                active_drugs=0,
                discontinued_drugs=0,
                last_updated=datetime.utcnow(),
                data_sources=[]
            )
    
    async def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("Drug database connection closed")


# Global instance
drug_db_manager = DrugDatabaseManager()
