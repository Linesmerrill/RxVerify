"""
Local Drug Search Service

This service provides fast drug search using our curated MongoDB database
instead of external API calls. Implements smart search logic based on query type.
"""

import logging
from typing import List, Dict, Any
from app.drug_database_manager import drug_db_manager
from app.drug_database_schema import DrugSearchResult

logger = logging.getLogger(__name__)


class LocalDrugSearchService:
    """Fast drug search service using local MongoDB database."""
    
    def __init__(self):
        self.search_count = 0
    
    async def initialize(self):
        """Initialize the search service."""
        try:
            await drug_db_manager.initialize()
            logger.info("Local drug search service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize local drug search service: {str(e)}")
            raise
    
    async def search_drugs(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for drugs using our local database.
        
        Smart search logic:
        - "metformin" → Show only generic Metformin
        - "Glucophage" → Show generic Metformin + brand info  
        - "metformin and glyburide" → Show combo drugs
        - "tylenol" → Show generic Acetaminophen + brand info
        """
        try:
            self.search_count += 1
            
            if not query or len(query.strip()) < 2:
                return []
            
            query = query.strip()
            logger.info(f"Searching local database for: '{query}'")
            
            # Search using our smart database manager
            search_results = await drug_db_manager.search_drugs(query, limit)
            
            # Convert to API response format
            api_results = []
            for result in search_results:
                api_results.append({
                    "drug_id": result.drug_id,
                    "name": result.name,
                    "generic_name": result.generic_name,
                    "brand_names": result.brand_names,
                    "common_uses": result.common_uses,
                    "drug_class": result.drug_class,
                    "source": "local_database",
                    "rxcui": result.rxnorm_id,
                    "url": "",
                    "drug_type": result.drug_type,
                    "manufacturer": result.manufacturer,
                    "relevance_score": result.relevance_score,
                    "match_type": result.match_type,
                    "rating_score": result.rating_score,
                    "total_votes": result.total_votes,
                    "upvotes": result.upvotes,
                    "downvotes": result.downvotes,
                    "is_hidden": result.is_hidden
                })
            
            logger.info(f"Found {len(api_results)} drugs for '{query}'")
            return api_results
            
        except Exception as e:
            logger.error(f"Local drug search failed for '{query}': {str(e)}")
            return []
    
    async def get_search_stats(self) -> Dict[str, Any]:
        """Get search statistics."""
        try:
            db_stats = await drug_db_manager.get_database_stats()
            return {
                "total_searches": self.search_count,
                "service_type": "local_drug_search",
                "caching_enabled": True,
                "fresh_results_only": False,
                "database_stats": {
                    "total_drugs": db_stats.total_drugs,
                    "generic_drugs": db_stats.generic_drugs,
                    "brand_drugs": db_stats.brand_drugs,
                    "combination_drugs": db_stats.combination_drugs,
                    "active_drugs": db_stats.active_drugs,
                    "last_updated": db_stats.last_updated.isoformat(),
                    "data_sources": db_stats.data_sources
                }
            }
        except Exception as e:
            logger.error(f"Failed to get search stats: {str(e)}")
            return {
                "total_searches": self.search_count,
                "service_type": "local_drug_search",
                "caching_enabled": True,
                "fresh_results_only": False,
                "database_stats": {}
            }
    
    async def get_drug_by_name(self, drug_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific drug."""
        try:
            # Search for exact match first
            results = await drug_db_manager.search_drugs(drug_name, 1)
            
            if results:
                result = results[0]
                return {
                    "drug_id": result.drug_id,
                    "name": result.name,
                    "generic_name": result.generic_name,
                    "brand_names": result.brand_names,
                    "drug_class": result.drug_class,
                    "common_uses": result.common_uses,
                    "manufacturer": result.manufacturer,
                    "rxnorm_id": result.rxnorm_id,
                    "drug_type": result.drug_type,
                    "relevance_score": result.relevance_score,
                    "match_type": result.match_type
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get drug by name '{drug_name}': {str(e)}")
            return {}
    
    async def get_common_uses(self, drug_name: str) -> List[str]:
        """Get common uses for a specific drug."""
        try:
            drug_info = await self.get_drug_by_name(drug_name)
            return drug_info.get("common_uses", [])
        except Exception as e:
            logger.error(f"Failed to get common uses for '{drug_name}': {str(e)}")
            return []
    
    async def suggest_drugs(self, partial_query: str, limit: int = 5) -> List[str]:
        """Get drug name suggestions for autocomplete."""
        try:
            if len(partial_query) < 2:
                return []
            
            results = await drug_db_manager.search_drugs(partial_query, limit)
            suggestions = [result.name for result in results]
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to get drug suggestions for '{partial_query}': {str(e)}")
            return []
    
    async def get_popular_drugs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most searched drugs."""
        try:
            # This would require a more complex query to get drugs sorted by search_count
            # For now, return empty list
            return []
        except Exception as e:
            logger.error(f"Failed to get popular drugs: {str(e)}")
            return []


# Global instance
local_drug_search_service = LocalDrugSearchService()
