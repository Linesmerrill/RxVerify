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
            rxnorm_results = await self.medical_api_client.search_rxnorm(query, limit * 3)  # Get more to filter
            
            # Format results for our drug model
            formatted_results = []
            for result in rxnorm_results:
                drug_name = result.get("name", "")
                
                # Skip complex pharmaceutical formulations
                if self._is_complex_formulation(drug_name):
                    continue
                
                # Skip generic terms
                if drug_name.lower() in ['oral', 'adverse', 'effect', 'side', 'drug', 'medication', 'tablet', 'capsule', 'injection']:
                    continue
                
                drug_data = {
                    "name": drug_name,
                    "generic_name": result.get("generic_name", ""),
                    "brand_names": result.get("brand_names", []),
                    "common_uses": result.get("common_uses", []),
                    "drug_class": result.get("drug_class", ""),
                    "source": "rxnorm"
                }
                
                formatted_results.append(drug_data)
                
                # Stop when we have enough good results
                if len(formatted_results) >= limit:
                    break
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching external APIs: {e}")
            return []
    
    def _is_complex_formulation(self, drug_name: str) -> bool:
        """Check if a drug name is a complex pharmaceutical formulation."""
        # Skip very long names (likely formulations)
        if len(drug_name) > 100:
            return True
        
        # Skip names with multiple ingredients (contain multiple MG/ML)
        if drug_name.count("MG/ML") > 1:
            return True
        
        # Skip names with complex chemical compositions
        complex_indicators = [
            "Injectable Solution",
            "Injectable Suspension", 
            "Topical Solution",
            "Oral Suspension",
            "Rectal Suppository",
            "Vaginal Suppository",
            "Ophthalmic Solution",
            "Otic Solution",
            "Nasal Spray",
            "Inhalation Solution",
            "Transdermal Patch",
            "Extended Release",
            "Delayed Release",
            "Controlled Release"
        ]
        
        for indicator in complex_indicators:
            if indicator in drug_name:
                return True
        
        return False
    
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
    
    async def populate_common_drugs(self) -> None:
        """Populate cache with common medications."""
        # Add some hardcoded common drugs for better results
        common_drugs_data = [
            {
                "name": "Metformin",
                "generic_name": "Metformin",
                "brand_names": ["Glucophage", "Fortamet", "Glumetza"],
                "common_uses": ["Type 2 Diabetes", "Blood Sugar Control"],
                "drug_class": "Biguanide",
                "source": "manual"
            },
            {
                "name": "Metoprolol",
                "generic_name": "Metoprolol",
                "brand_names": ["Lopressor", "Toprol XL"],
                "common_uses": ["High Blood Pressure", "Heart Disease", "Chest Pain"],
                "drug_class": "Beta Blocker",
                "source": "manual"
            },
            {
                "name": "Aspirin",
                "generic_name": "Aspirin",
                "brand_names": ["Bayer", "Ecotrin", "Bufferin"],
                "common_uses": ["Pain Relief", "Fever Reduction", "Heart Attack Prevention"],
                "drug_class": "NSAID",
                "source": "manual"
            },
            {
                "name": "Atorvastatin",
                "generic_name": "Atorvastatin",
                "brand_names": ["Lipitor"],
                "common_uses": ["High Cholesterol", "Heart Disease Prevention"],
                "drug_class": "Statin",
                "source": "manual"
            },
            {
                "name": "Lisinopril",
                "generic_name": "Lisinopril",
                "brand_names": ["Prinivil", "Zestril"],
                "common_uses": ["High Blood Pressure", "Heart Failure"],
                "drug_class": "ACE Inhibitor",
                "source": "manual"
            }
        ]
        
        # Cache the hardcoded drugs
        for drug_data in common_drugs_data:
            await mongodb_manager.cache_drug(drug_data)
        
        # Also try to populate from APIs
        common_drug_names = [
            "metformin", "metoprolol", "methotrexate", "methylprednisolone",
            "aspirin", "acetaminophen", "ibuprofen", "naproxen",
            "atorvastatin", "simvastatin", "pravastatin", "rosuvastatin",
            "lisinopril", "enalapril", "ramipril", "captopril"
        ]
        
        await self.populate_initial_cache(common_drug_names)

# Global drug search service instance
drug_search_service = DrugSearchService()
