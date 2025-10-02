"""Fast medication search service for autocomplete functionality."""

import asyncio
import time
import re
from typing import List, Dict, Optional, Set
from app.models import DrugSearchResult, Source
from app.medical_apis import get_medical_api_client
from app.medication_cache import get_medication_cache
import logging

logger = logging.getLogger(__name__)

class MedicationSearchService:
    """Fast medication search service optimized for autocomplete."""
    
    def __init__(self):
        self._common_uses_cache = {}
        self._drug_class_cache = {}
        self._medication_cache = get_medication_cache()
    
    async def search_medications(self, query: str, limit: int = 10) -> List[DrugSearchResult]:
        """
        Fast medication search optimized for autocomplete with caching.
        Returns accurate drug information with common uses.
        """
        start_time = time.time()
        
        if not query or len(query.strip()) < 2:
            return []
        
        query = query.strip().lower()
        
        try:
            # 1. First check cache for fast results
            cached_results = self._medication_cache.search_medications(query, limit)
            if cached_results:
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Cache search completed in {processing_time:.2f}ms for query: '{query}'")
                return cached_results
            
            # 2. Try local fallback for common drugs and partial matches
            local_results = self._search_local_drugs(query, limit)
            if local_results:
                # Cache the local results for future searches
                self._medication_cache.cache_medications(local_results)
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Local search completed in {processing_time:.2f}ms for query: '{query}'")
                return local_results
            
            # 3. Search RxNorm API for new medications
            api_client = await get_medical_api_client()
            rxnorm_results = await self._search_rxnorm_fast(api_client, query, limit)
            
            # 4. Enhance results with additional information
            enhanced_results = await self._enhance_search_results(rxnorm_results, query)
            
            # 5. Sort by relevance (exact matches first, then partial matches)
            sorted_results = self._sort_by_relevance(enhanced_results, query)
            
            # 6. Consolidate medications with same common uses
            consolidated_results = self._consolidate_medications(sorted_results)
            
            # 7. Limit results
            final_results = consolidated_results[:limit]
            
            # 8. Cache the results for future fast lookups
            if final_results:
                self._medication_cache.cache_medications(final_results)
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"RxNorm search completed in {processing_time:.2f}ms for query: '{query}'")
            
            return final_results
            
        except Exception as e:
            logger.error(f"Medication search failed for query '{query}': {str(e)}")
            return []
    
    def _search_local_drugs(self, query: str, limit: int) -> List[DrugSearchResult]:
        """Search local database of common drugs for partial matches."""
        # Common drugs database with partial name matching
        common_drugs = {
            # Tylenol/Acetaminophen
            "tyl": ["acetaminophen", "tylenol"],
            "acet": ["acetaminophen", "tylenol"],
            "tylenol": ["acetaminophen", "tylenol"],
            "acetaminophen": ["acetaminophen", "tylenol"],
            
            # Aspirin
            "asp": ["aspirin"],
            "aspirin": ["aspirin"],
            
            # Ibuprofen
            "ibu": ["ibuprofen", "advil", "motrin"],
            "ibuprofen": ["ibuprofen", "advil", "motrin"],
            "advil": ["ibuprofen", "advil", "motrin"],
            "motrin": ["ibuprofen", "advil", "motrin"],
            
            # Metformin
            "met": ["metformin"],
            "metformin": ["metformin"],
            
            # Atorvastatin/Lipitor
            "ato": ["atorvastatin", "lipitor"],
            "atorvastatin": ["atorvastatin", "lipitor"],
            "lipitor": ["atorvastatin", "lipitor"],
            
            # Lisinopril
            "lis": ["lisinopril"],
            "lisinopril": ["lisinopril"],
            
            # Simvastatin
            "sim": ["simvastatin", "zocor"],
            "simvastatin": ["simvastatin", "zocor"],
            "zocor": ["simvastatin", "zocor"],
            
            # Omeprazole
            "ome": ["omeprazole", "prilosec"],
            "omeprazole": ["omeprazole", "prilosec"],
            "prilosec": ["omeprazole", "prilosec"],
            
            # Amoxicillin
            "amox": ["amoxicillin"],
            "amoxicillin": ["amoxicillin"],
            
            # Sertraline
            "ser": ["sertraline", "zoloft"],
            "sertraline": ["sertraline", "zoloft"],
            "zoloft": ["sertraline", "zoloft"],
            
            # Fluoxetine
            "flu": ["fluoxetine", "prozac"],
            "fluoxetine": ["fluoxetine", "prozac"],
            "prozac": ["fluoxetine", "prozac"],
        }
        
        # Check for exact matches first
        if query in common_drugs:
            drug_names = common_drugs[query]
            results = []
            seen_rxcuis = set()
            
            # Prioritize brand names over generic names
            brand_names = [name for name in drug_names if name.lower() in ['tylenol', 'advil', 'motrin', 'lipitor', 'zocor', 'prilosec', 'zoloft', 'prozac']]
            generic_names = [name for name in drug_names if name not in brand_names]
            prioritized_names = brand_names + generic_names
            
            for drug_name in prioritized_names[:limit]:
                result = self._create_drug_result(drug_name)
                if result and result.rxcui not in seen_rxcuis:
                    results.append(result)
                    seen_rxcuis.add(result.rxcui)
            
            return results
        
        # Check for partial matches
        results = []
        seen_rxcuis = set()
        for key, drug_names in common_drugs.items():
            if query in key and len(query) >= 3:  # Only for queries 3+ chars
                # Prioritize brand names over generic names
                brand_names = [name for name in drug_names if name.lower() in ['tylenol', 'advil', 'motrin', 'lipitor', 'zocor', 'prilosec', 'zoloft', 'prozac']]
                generic_names = [name for name in drug_names if name not in brand_names]
                prioritized_names = brand_names + generic_names
                
                for drug_name in prioritized_names:
                    if len(results) >= limit:
                        break
                    result = self._create_drug_result(drug_name)
                    if result and result.rxcui not in seen_rxcuis:
                        results.append(result)
                        seen_rxcuis.add(result.rxcui)
        
        return results[:limit]
    
    def _create_drug_result(self, drug_name: str) -> DrugSearchResult:
        """Create a DrugSearchResult from a drug name."""
        # Drug information database
        drug_info = {
            "acetaminophen": {
                "rxcui": "161",
                "name": "acetaminophen",
                "generic_name": "acetaminophen",
                "brand_names": ["Tylenol"],
                "common_uses": ["Pain relief", "Fever reduction"],
                "drug_class": "Analgesic/Antipyretic"
            },
            "tylenol": {
                "rxcui": "161",
                "name": "Tylenol",
                "generic_name": "acetaminophen",
                "brand_names": ["Tylenol"],
                "common_uses": ["Pain relief", "Fever reduction"],
                "drug_class": "Analgesic/Antipyretic"
            },
            "aspirin": {
                "rxcui": "1191",
                "name": "aspirin",
                "generic_name": "aspirin",
                "brand_names": ["Bayer", "Ecotrin"],
                "common_uses": ["Pain relief", "Fever reduction", "Heart attack prevention", "Stroke prevention"],
                "drug_class": "Salicylate (NSAID)"
            },
            "ibuprofen": {
                "rxcui": "5640",
                "name": "ibuprofen",
                "generic_name": "ibuprofen",
                "brand_names": ["Advil", "Motrin"],
                "common_uses": ["Pain relief", "Inflammation", "Fever reduction"],
                "drug_class": "NSAID (Non-steroidal Anti-inflammatory)"
            },
            "advil": {
                "rxcui": "5640",
                "name": "Advil",
                "generic_name": "ibuprofen",
                "brand_names": ["Advil", "Motrin"],
                "common_uses": ["Pain relief", "Inflammation", "Fever reduction"],
                "drug_class": "NSAID (Non-steroidal Anti-inflammatory)"
            },
            "motrin": {
                "rxcui": "5640",
                "name": "Motrin",
                "generic_name": "ibuprofen",
                "brand_names": ["Advil", "Motrin"],
                "common_uses": ["Pain relief", "Inflammation", "Fever reduction"],
                "drug_class": "NSAID (Non-steroidal Anti-inflammatory)"
            },
            "metformin": {
                "rxcui": "6809",
                "name": "metformin",
                "generic_name": "metformin",
                "brand_names": ["Glucophage"],
                "common_uses": ["Type 2 diabetes", "Polycystic ovary syndrome"],
                "drug_class": "Biguanide (Diabetes Medication)"
            },
            "atorvastatin": {
                "rxcui": "617312",
                "name": "atorvastatin",
                "generic_name": "atorvastatin",
                "brand_names": ["Lipitor"],
                "common_uses": ["High cholesterol", "Cardiovascular disease prevention"],
                "drug_class": "HMG-CoA Reductase Inhibitor (Statin)"
            },
            "lipitor": {
                "rxcui": "617312",
                "name": "Lipitor",
                "generic_name": "atorvastatin",
                "brand_names": ["Lipitor"],
                "common_uses": ["High cholesterol", "Cardiovascular disease prevention"],
                "drug_class": "HMG-CoA Reductase Inhibitor (Statin)"
            },
            "lisinopril": {
                "rxcui": "314076",
                "name": "lisinopril",
                "generic_name": "lisinopril",
                "brand_names": ["Prinivil", "Zestril"],
                "common_uses": ["High blood pressure", "Heart failure", "Kidney protection in diabetes"],
                "drug_class": "ACE Inhibitor"
            },
            "simvastatin": {
                "rxcui": "36567",
                "name": "simvastatin",
                "generic_name": "simvastatin",
                "brand_names": ["Zocor"],
                "common_uses": ["High cholesterol", "Cardiovascular disease prevention"],
                "drug_class": "HMG-CoA Reductase Inhibitor (Statin)"
            },
            "zocor": {
                "rxcui": "36567",
                "name": "Zocor",
                "generic_name": "simvastatin",
                "brand_names": ["Zocor"],
                "common_uses": ["High cholesterol", "Cardiovascular disease prevention"],
                "drug_class": "HMG-CoA Reductase Inhibitor (Statin)"
            },
            "omeprazole": {
                "rxcui": "7646",
                "name": "omeprazole",
                "generic_name": "omeprazole",
                "brand_names": ["Prilosec"],
                "common_uses": ["Acid reflux", "Stomach ulcers", "GERD"],
                "drug_class": "Proton Pump Inhibitor (PPI)"
            },
            "prilosec": {
                "rxcui": "7646",
                "name": "Prilosec",
                "generic_name": "omeprazole",
                "brand_names": ["Prilosec"],
                "common_uses": ["Acid reflux", "Stomach ulcers", "GERD"],
                "drug_class": "Proton Pump Inhibitor (PPI)"
            },
            "amoxicillin": {
                "rxcui": "7947",
                "name": "amoxicillin",
                "generic_name": "amoxicillin",
                "brand_names": ["Amoxil"],
                "common_uses": ["Bacterial infections"],
                "drug_class": "Penicillin Antibiotic"
            },
            "sertraline": {
                "rxcui": "8787",
                "name": "sertraline",
                "generic_name": "sertraline",
                "brand_names": ["Zoloft"],
                "common_uses": ["Depression", "Anxiety", "Panic disorder"],
                "drug_class": "SSRI (Selective Serotonin Reuptake Inhibitor)"
            },
            "zoloft": {
                "rxcui": "8787",
                "name": "Zoloft",
                "generic_name": "sertraline",
                "brand_names": ["Zoloft"],
                "common_uses": ["Depression", "Anxiety", "Panic disorder"],
                "drug_class": "SSRI (Selective Serotonin Reuptake Inhibitor)"
            },
            "fluoxetine": {
                "rxcui": "4234",
                "name": "fluoxetine",
                "generic_name": "fluoxetine",
                "brand_names": ["Prozac"],
                "common_uses": ["Depression", "Anxiety", "Obsessive-compulsive disorder"],
                "drug_class": "SSRI (Selective Serotonin Reuptake Inhibitor)"
            },
            "prozac": {
                "rxcui": "4234",
                "name": "Prozac",
                "generic_name": "fluoxetine",
                "brand_names": ["Prozac"],
                "common_uses": ["Depression", "Anxiety", "Obsessive-compulsive disorder"],
                "drug_class": "SSRI (Selective Serotonin Reuptake Inhibitor)"
            }
        }
        
        if drug_name.lower() in drug_info:
            info = drug_info[drug_name.lower()]
            return DrugSearchResult(
                rxcui=info["rxcui"],
                name=info["name"],
                generic_name=info["generic_name"],
                brand_names=info["brand_names"],
                common_uses=info["common_uses"],
                drug_class=info["drug_class"],
                source="local"
            )
        
        return None
    
    async def _search_rxnorm_fast(self, api_client, query: str, limit: int) -> List[Dict]:
        """Fast RxNorm search for drug names and synonyms."""
        try:
            # Use RxNorm's drug search API
            search_url = "https://rxnav.nlm.nih.gov/REST/drugs.json"
            params = {
                "name": query,
                "allsrc": 1,
                "src": 1
            }
            
            response = await api_client.http_client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "drugGroup" in data and "conceptGroup" in data["drugGroup"]:
                for concept_group in data["drugGroup"]["conceptGroup"]:
                    if "conceptProperties" in concept_group:
                        for concept in concept_group["conceptProperties"][:limit * 2]:  # Get more for filtering
                            results.append({
                                "rxcui": concept.get("rxcui", ""),
                                "name": concept.get("name", ""),
                                "term_type": concept.get("termType", ""),
                                "source": "rxnorm"
                            })
            
            return results
            
        except Exception as e:
            logger.error(f"RxNorm search failed: {str(e)}")
            return []
    
    async def _enhance_search_results(self, results: List[Dict], query: str) -> List[DrugSearchResult]:
        """Enhance search results with additional drug information."""
        enhanced_results = []
        seen_rxcuis = set()
        
        for result in results:
            rxcui = result.get("rxcui")
            if not rxcui or rxcui in seen_rxcuis:
                continue
                
            seen_rxcuis.add(rxcui)
            
            # Get additional drug information
            drug_info = await self._get_drug_details(rxcui, result["name"])
            
            # Create search result
            search_result = DrugSearchResult(
                rxcui=rxcui,
                name=result["name"],
                generic_name=drug_info.get("generic_name"),
                brand_names=drug_info.get("brand_names", []),
                common_uses=drug_info.get("common_uses", []),
                drug_class=drug_info.get("drug_class"),
                source="rxnorm"
            )
            
            enhanced_results.append(search_result)
        
        return enhanced_results
    
    async def _get_drug_details(self, rxcui: str, name: str) -> Dict:
        """Get additional drug details including common uses."""
        try:
            # Get drug properties from RxNorm
            api_client = await get_medical_api_client()
            
            # Get drug properties
            props_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
            props_response = await api_client.http_client.get(props_url)
            
            drug_info = {
                "generic_name": None,
                "brand_names": [],
                "common_uses": [],
                "drug_class": None
            }
            
            if props_response.status_code == 200:
                props_data = props_response.json()
                if "properties" in props_data:
                    props = props_data["properties"]
                    drug_info["generic_name"] = props.get("name")
            
            # Get related concepts (brand names, etc.)
            related_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json?tty=BN"
            related_response = await api_client.http_client.get(related_url)
            
            if related_response.status_code == 200:
                related_data = related_response.json()
                if "relatedGroup" in related_data and "conceptGroup" in related_data["relatedGroup"]:
                    for concept_group in related_data["relatedGroup"]["conceptGroup"]:
                        if "conceptProperties" in concept_group:
                            for concept in concept_group["conceptProperties"]:
                                brand_name = concept.get("name", "")
                                if brand_name and brand_name not in drug_info["brand_names"]:
                                    drug_info["brand_names"].append(brand_name)
            
            # Add common uses based on drug name patterns and known information
            drug_info["common_uses"] = self._get_common_uses(name, rxcui)
            
            # Determine drug class
            drug_info["drug_class"] = self._determine_drug_class(name)
            
            return drug_info
            
        except Exception as e:
            logger.error(f"Failed to get drug details for {rxcui}: {str(e)}")
            return {
                "generic_name": None,
                "brand_names": [],
                "common_uses": self._get_common_uses(name, rxcui),
                "drug_class": self._determine_drug_class(name)
            }
    
    def _get_common_uses(self, name: str, rxcui: str) -> List[str]:
        """Get common uses for a medication based on known patterns."""
        name_lower = name.lower()
        
        # Common drug classes and their uses
        drug_uses = {
            # Statins
            "atorvastatin": ["High cholesterol", "Cardiovascular disease prevention"],
            "simvastatin": ["High cholesterol", "Cardiovascular disease prevention"],
            "rosuvastatin": ["High cholesterol", "Cardiovascular disease prevention"],
            "pravastatin": ["High cholesterol", "Cardiovascular disease prevention"],
            
            # ACE Inhibitors
            "lisinopril": ["High blood pressure", "Heart failure", "Kidney protection in diabetes"],
            "enalapril": ["High blood pressure", "Heart failure"],
            "ramipril": ["High blood pressure", "Heart failure", "Cardiovascular protection"],
            
            # Beta Blockers
            "metoprolol": ["High blood pressure", "Heart rhythm disorders", "Heart failure"],
            "atenolol": ["High blood pressure", "Heart rhythm disorders"],
            "propranolol": ["High blood pressure", "Heart rhythm disorders", "Anxiety"],
            
            # Diabetes medications
            "metformin": ["Type 2 diabetes", "Polycystic ovary syndrome"],
            "glipizide": ["Type 2 diabetes"],
            "glyburide": ["Type 2 diabetes"],
            
            # Pain medications
            "acetaminophen": ["Pain relief", "Fever reduction"],
            "ibuprofen": ["Pain relief", "Inflammation", "Fever reduction"],
            "naproxen": ["Pain relief", "Inflammation"],
            "aspirin": ["Pain relief", "Fever reduction", "Heart attack prevention", "Stroke prevention"],
            
            # Antibiotics
            "amoxicillin": ["Bacterial infections"],
            "azithromycin": ["Bacterial infections"],
            "ciprofloxacin": ["Bacterial infections"],
            
            # Antidepressants
            "sertraline": ["Depression", "Anxiety", "Panic disorder"],
            "fluoxetine": ["Depression", "Anxiety", "Obsessive-compulsive disorder"],
            "escitalopram": ["Depression", "Anxiety"],
            
            # Proton pump inhibitors
            "omeprazole": ["Acid reflux", "Stomach ulcers", "GERD"],
            "pantoprazole": ["Acid reflux", "Stomach ulcers", "GERD"],
            "lansoprazole": ["Acid reflux", "Stomach ulcers", "GERD"],
            
            # Antiparasitic
            "ivermectin": ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"],
        }
        
        # Check for exact matches first
        for drug, uses in drug_uses.items():
            if drug in name_lower:
                return uses
        
        # Check for partial matches
        for drug, uses in drug_uses.items():
            if any(word in name_lower for word in drug.split()):
                return uses
        
        # Generic patterns based on drug name endings
        if any(suffix in name_lower for suffix in ["statin", "vastatin"]):
            return ["High cholesterol", "Cardiovascular disease prevention"]
        elif any(suffix in name_lower for suffix in ["pril", "sartan"]):
            return ["High blood pressure", "Heart conditions"]
        elif any(suffix in name_lower for suffix in ["olol", "lol"]):
            return ["High blood pressure", "Heart rhythm disorders"]
        elif any(suffix in name_lower for suffix in ["mycin", "cillin", "floxacin"]):
            return ["Bacterial infections"]
        elif any(suffix in name_lower for suffix in ["prazole", "tidine"]):
            return ["Acid reflux", "Stomach conditions"]
        elif any(suffix in name_lower for suffix in ["pam", "zepam", "pine"]):
            return ["Anxiety", "Sleep disorders"]
        elif any(suffix in name_lower for suffix in ["mectin", "vermectin"]):
            return ["Parasitic infections", "Scabies", "Head lice"]
        
        # Default fallback
        return ["Medication"]
    
    def _determine_drug_class(self, name: str) -> Optional[str]:
        """Determine drug class based on name patterns."""
        name_lower = name.lower()
        
        drug_classes = {
            "statin": "HMG-CoA Reductase Inhibitor (Statin)",
            "vastatin": "HMG-CoA Reductase Inhibitor (Statin)",
            "pril": "ACE Inhibitor",
            "sartan": "Angiotensin Receptor Blocker (ARB)",
            "olol": "Beta Blocker",
            "mycin": "Antibiotic",
            "cillin": "Penicillin Antibiotic",
            "floxacin": "Fluoroquinolone Antibiotic",
            "prazole": "Proton Pump Inhibitor (PPI)",
            "tidine": "H2 Blocker",
            "pam": "Benzodiazepine",
            "zepam": "Benzodiazepine",
            "pine": "Calcium Channel Blocker",
            "formin": "Biguanide (Diabetes Medication)",
            "glide": "Sulfonylurea (Diabetes Medication)",
            "triptan": "Triptan (Migraine Medication)",
            "coxib": "COX-2 Inhibitor (NSAID)",
            "profen": "NSAID (Non-steroidal Anti-inflammatory)",
            "cet": "NSAID (Non-steroidal Anti-inflammatory)",
            "aspirin": "Salicylate (NSAID)",
        }
        
        for pattern, drug_class in drug_classes.items():
            if pattern in name_lower:
                return drug_class
        
        return None
    
    def _sort_by_relevance(self, results: List[DrugSearchResult], query: str) -> List[DrugSearchResult]:
        """Sort results by relevance to the search query."""
        query_lower = query.lower()
        
        def relevance_score(result: DrugSearchResult) -> int:
            score = 0
            name_lower = result.name.lower()
            
            # Exact match gets highest score
            if name_lower == query_lower:
                score += 1000
            
            # Starts with query gets high score
            elif name_lower.startswith(query_lower):
                score += 500
            
            # Contains query gets medium score
            elif query_lower in name_lower:
                score += 200
            
            # Generic name matches get bonus
            if result.generic_name and query_lower in result.generic_name.lower():
                score += 100
            
            # Brand name matches get bonus
            for brand in result.brand_names:
                if query_lower in brand.lower():
                    score += 50
            
            # Shorter names get slight bonus (more specific)
            score += max(0, 50 - len(result.name))
            
            return score
        
        return sorted(results, key=relevance_score, reverse=True)
    
    def _consolidate_medications(self, results: List[DrugSearchResult]) -> List[DrugSearchResult]:
        """Consolidate medications with identical common uses into single results."""
        if not results:
            return results
        
        # Group by common uses (sorted for consistency)
        groups = {}
        for result in results:
            # Create a key from sorted common uses
            uses_key = tuple(sorted(result.common_uses)) if result.common_uses else ("Medication",)
            
            if uses_key not in groups:
                groups[uses_key] = []
            groups[uses_key].append(result)
        
        consolidated = []
        for uses_key, group in groups.items():
            if len(group) == 1:
                # Single medication, keep as is
                consolidated.append(group[0])
            else:
                # Multiple medications with same uses, consolidate
                consolidated_result = self._merge_medications(group)
                consolidated.append(consolidated_result)
        
        return consolidated
    
    def _merge_medications(self, medications: List[DrugSearchResult]) -> DrugSearchResult:
        """Merge multiple medications with same common uses into one result."""
        if not medications:
            return None
        
        if len(medications) == 1:
            return medications[0]
        
        # Use the first medication as base
        base = medications[0]
        
        # Collect all unique brand names
        all_brand_names = set(base.brand_names)
        for med in medications[1:]:
            all_brand_names.update(med.brand_names)
        
        # Create a generic name that represents the drug class
        # Extract the base drug name (e.g., "ivermectin" from "ivermectin 6 MG Oral Tablet")
        base_name = self._extract_base_drug_name(base.name)
        
        # Create consolidated result
        consolidated = DrugSearchResult(
            rxcui=base.rxcui,  # Use first RxCUI
            name=base_name,
            generic_name=base_name,
            brand_names=list(all_brand_names),
            common_uses=base.common_uses,
            drug_class=base.drug_class,
            source=base.source
        )
        
        return consolidated
    
    def _extract_base_drug_name(self, full_name: str) -> str:
        """Extract the base drug name from a full medication name."""
        import re
        
        # Remove common suffixes and dosage information
        name = full_name.lower()
        
        # Remove dosage patterns (more comprehensive)
        name = re.sub(r'\d+\s*(mg|mcg|g|ml|%|mg/ml|mcg/ml)\s*', '', name)
        name = re.sub(r'\s*(oral|topical|injection|cream|lotion|tablet|solution|capsule|gel|drops|spray|patch)\s*', '', name)
        name = re.sub(r'\[.*?\]', '', name)  # Remove bracketed text
        name = re.sub(r'\(.*?\)', '', name)  # Remove parenthetical text
        name = re.sub(r'\s+', ' ', name).strip()  # Clean up spaces
        
        # If we have multiple words, take the first meaningful word
        words = name.split()
        if words:
            # Take the first word that looks like a drug name (not empty, not just numbers/symbols)
            for word in words:
                if word and not re.match(r'^[\d\.\-\/]+$', word):
                    return word.capitalize()
        
        # Fallback to original name if extraction fails
        return full_name

# Global search service instance
_search_service = None

async def get_search_service() -> MedicationSearchService:
    """Get or create the global search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = MedicationSearchService()
    return _search_service
