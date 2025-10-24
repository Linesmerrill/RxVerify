"""Drug search service with drugs.com-style autocomplete and caching.

This service provides fast drug search with autocomplete functionality,
caching results in MongoDB for improved performance.
"""

import asyncio
import httpx
import logging
from typing import List, Dict, Optional, Any
from app.mongodb_manager import mongodb_manager
from app.medical_apis import MedicalAPIClient

logger = logging.getLogger(__name__)

class DrugSearchService:
    """Service for drug search with caching and autocomplete."""
    
    def __init__(self):
        self.medical_api_client = MedicalAPIClient()
        self.cache_hit_count = 0
        self.cache_miss_count = 0
    
    async def search_drugs(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for drugs with caching - drugs.com style autocomplete."""
        if not query or len(query.strip()) < 2:
            return []
        
        query = query.strip().lower()
        
        try:
            # First, try to get results from cache
            cached_results = await mongodb_manager.search_drugs(query, limit)
            
            if cached_results:
                logger.info(f"Cache hit for query: {query}")
                self.cache_hit_count += 1
                return self._format_results(cached_results)
            
            # Cache miss - search external APIs
            logger.info(f"Cache miss for query: {query}, searching external APIs")
            self.cache_miss_count += 1
            
            # Search RxNorm for drug names
            api_results = await self._search_external_apis(query, limit)
            
            # Cache the results for future use
            await self._cache_results(api_results)
            
            return self._format_results(api_results)
            
        except Exception as e:
            logger.error(f"Error in drug search: {e}")
            return []
    
    async def _search_external_apis(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search external APIs for drug information."""
        try:
            # Use RxNorm for drug name search
            rxnorm_results = await self.medical_api_client.search_rxnorm(query, limit)
            
            # Format results for our drug model
            formatted_results = []
            for result in rxnorm_results:
                drug_data = {
                    "name": result.get("name", ""),
                    "generic_name": result.get("generic_name", ""),
                    "brand_names": result.get("brand_names", []),
                    "common_uses": result.get("common_uses", []),
                    "drug_class": result.get("drug_class", ""),
                    "source": "rxnorm"
                }
                
                # Only include if we have a valid name
                if drug_data["name"] and drug_data["name"].lower() not in ['oral', 'adverse', 'effect', 'side', 'drug', 'medication']:
                    formatted_results.append(drug_data)
            
            return formatted_results[:limit]
            
        except Exception as e:
            logger.error(f"Error searching external APIs: {e}")
            return []
    
    async def _cache_results(self, results: List[Dict[str, Any]]) -> None:
        """Cache search results in MongoDB."""
        try:
            for drug_data in results:
                await mongodb_manager.cache_drug(drug_data)
            logger.info(f"Cached {len(results)} drug results")
        except Exception as e:
            logger.error(f"Error caching results: {e}")
    
    def _format_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format results for frontend consumption."""
        formatted = []
        
        for result in results:
            # Create a clean drug name
            drug_name = result.get("name", "")
            generic_name = result.get("generic_name", "")
            
            # Use generic name if available and different from name
            display_name = generic_name if generic_name and generic_name != drug_name else drug_name
            
            formatted_result = {
                "name": display_name,
                "generic_name": generic_name,
                "brand_names": result.get("brand_names", []),
                "common_uses": result.get("common_uses", []),
                "drug_class": result.get("drug_class", ""),
                "source": result.get("source", "rxnorm")
            }
            
            formatted.append(formatted_result)
        
        return formatted
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        return {
            "cache_hits": self.cache_hit_count,
            "cache_misses": self.cache_miss_count,
            "hit_rate": self.cache_hit_count / (self.cache_hit_count + self.cache_miss_count) if (self.cache_hit_count + self.cache_miss_count) > 0 else 0
        }
    
    async def populate_initial_cache(self, common_drugs: List[str]) -> None:
        """Populate cache with common drugs for better initial performance."""
        logger.info(f"Populating cache with {len(common_drugs)} common drugs")
        
        for drug_name in common_drugs:
            try:
                # Search for each drug to populate cache
                await self.search_drugs(drug_name, limit=1)
                await asyncio.sleep(0.1)  # Small delay to avoid overwhelming APIs
            except Exception as e:
                logger.error(f"Error populating cache for {drug_name}: {e}")

# Global drug search service instance
drug_search_service = DrugSearchService()
