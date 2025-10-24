"""Enhanced search service for post-hospital discharge medications.

This service focuses on oral medications commonly prescribed after hospital stays,
using real-time API calls and vector search to provide curated, relevant results.
"""

import asyncio
import time
import re
from typing import List, Dict, Optional, Set, Tuple
from app.models import DrugSearchResult, Source
from app.medical_apis import get_medical_api_client
from app.embeddings import embed
from app.db import search_vector, add_document
from app.feedback_database import FeedbackDatabase
import logging

logger = logging.getLogger(__name__)

class PostDischargeSearchService:
    """Enhanced search service for post-hospital discharge medications."""
    
    def __init__(self):
        self._medication_cache = {}
        self._feedback_db = FeedbackDatabase()  # Persistent feedback storage
        
        # Common post-hospital discharge medication patterns
        self._discharge_med_patterns = [
            # Cardiovascular
            r'\b(atorvastatin|simvastatin|rosuvastatin|pravastatin)\b',  # Statins
            r'\b(metoprolol|atenolol|propranolol|carvedilol)\b',  # Beta blockers
            r'\b(lisinopril|enalapril|ramipril|captopril)\b',  # ACE inhibitors
            r'\b(losartan|valsartan|candesartan|irbesartan)\b',  # ARBs
            r'\b(amlodipine|nifedipine|diltiazem|verapamil)\b',  # Calcium channel blockers
            
            # Diabetes
            r'\b(metformin|glipizide|glyburide|pioglitazone)\b',  # Diabetes meds
            
            # Gastrointestinal
            r'\b(omeprazole|lansoprazole|pantoprazole|esomeprazole)\b',  # PPIs
            r'\b(ranitidine|famotidine|cimetidine)\b',  # H2 blockers
            
            # Pain management
            r'\b(acetaminophen|ibuprofen|naproxen|tramadol)\b',  # Pain meds
            
            # Antibiotics
            r'\b(amoxicillin|azithromycin|ciprofloxacin|doxycycline)\b',  # Common antibiotics
            
            # Anticoagulants
            r'\b(warfarin|apixaban|rivaroxaban|dabigatran)\b',  # Blood thinners
            
            # Respiratory
            r'\b(albuterol|fluticasone|budesonide|montelukast)\b',  # Asthma/COPD
        ]
        
        # Exclude patterns (IV, formulas, drip bags, etc.)
        self._exclude_patterns = [
            r'\b(iv|intravenous|injection|injectable)\b',
            r'\b(formula|solution|drip|infusion)\b',
            r'\b(cream|ointment|gel|patch|suppository)\b',
            r'\b(inhaler|nebulizer|aerosol)\b',
            r'\b(eye drops|ear drops|nasal spray)\b',
            r'\b(chewable|dispersible|effervescent)\b',
        ]
    
    async def search_discharge_medications(self, query: str, limit: int = 10) -> List[DrugSearchResult]:
        """Search for post-hospital discharge medications with enhanced filtering."""
        start_time = time.time()
        
        if not query or len(query.strip()) < 2:
            return []
        
        query = query.strip().lower()
        logger.info(f"Searching discharge medications for: '{query}'")
        
        try:
            # 1. Check if this looks like a post-discharge medication query
            is_discharge_query = self._is_discharge_medication_query(query)
            
            # 2. Search using real-time APIs with discharge focus
            api_results = await self._search_apis_for_discharge_meds(query, limit, is_discharge_query)
            
            # 3. Filter for oral medications only
            oral_results = self._filter_oral_medications(api_results)
            
            # 4. Enhance with vector search for additional context
            enhanced_results = await self._enhance_with_vector_search(query, oral_results)
            
            # 5. Apply ML feedback scoring and filtering
            scored_results = self._apply_feedback_scoring(enhanced_results, query)
            
            # 6. Filter out ignored medications
            filtered_results = self._filter_ignored_medications(scored_results, query)
            
            # 7. Sort by relevance and discharge medication priority
            final_results = self._sort_by_discharge_relevance(filtered_results, query)
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Discharge medication search completed in {processing_time:.2f}ms, found {len(final_results)} results")
            
            return final_results[:limit]
            
        except Exception as e:
            logger.error(f"Error in discharge medication search: {str(e)}")
            return []
    
    def _is_discharge_medication_query(self, query: str) -> bool:
        """Check if the query is likely for post-discharge medications."""
        discharge_indicators = [
            'discharge', 'after hospital', 'post hospital', 'going home',
            'prescription', 'medication', 'pill', 'tablet', 'capsule',
            'daily', 'twice daily', 'once daily', 'morning', 'evening'
        ]
        
        return any(indicator in query for indicator in discharge_indicators)
    
    async def _search_apis_for_discharge_meds(self, query: str, limit: int, is_discharge_query: bool) -> List[DrugSearchResult]:
        """Search medical APIs with focus on discharge medications."""
        api_client = await get_medical_api_client()
        
        # Adjust search strategy based on query type
        if is_discharge_query:
            # For discharge queries, prioritize common oral medications
            daily_med_limit = max(3, limit // 3)
            rxnorm_limit = max(4, limit // 2)  # More from RxNorm for drug names
            openfda_limit = max(2, limit // 4)
            drugbank_limit = max(1, limit // 4)
        else:
            # Standard distribution
            daily_med_limit = max(2, limit // 4)
            rxnorm_limit = max(3, limit // 3)
            openfda_limit = max(2, limit // 4)
            drugbank_limit = max(2, limit // 4)
        
        # Search all sources concurrently
        search_results = await api_client.search_all_sources_custom(
            query, daily_med_limit, openfda_limit, rxnorm_limit, drugbank_limit
        )
        
        # Convert RetrievedDoc to DrugSearchResult
        results = []
        for doc in search_results:
            logger.debug(f"Processing doc: title='{doc.title}', rxcui='{doc.rxcui}', source='{doc.source}'")
            drug_result = self._convert_to_drug_search_result(doc, query)
            if drug_result:
                logger.debug(f"Created drug result: name='{drug_result.name}', rxcui='{drug_result.rxcui}'")
                results.append(drug_result)
            else:
                logger.debug(f"Failed to create drug result from doc: title='{doc.title}'")
        
        # Combine duplicate drugs with different dosages
        results = self._combine_duplicate_drugs(results)
        
        return results
    
    def _convert_to_drug_search_result(self, doc, query: str) -> Optional[DrugSearchResult]:
        """Convert RetrievedDoc to DrugSearchResult."""
        try:
            # Use the title as the primary drug name (this comes from the API response)
            drug_name = doc.title
            if not drug_name or drug_name.lower() in ['oral', 'adverse', 'effect', 'side', 'drug', 'medication']:
                # Fallback to extracting from text
                drug_name = self._extract_drug_name(doc.text)
                if not drug_name:
                    return None
            
            # Clean up the drug name
            drug_name = self._clean_drug_name(drug_name)
            
            # Filter out non-drug results
            if self._is_invalid_drug_name(drug_name):
                return None
            
            # Extract additional information
            generic_name = self._extract_generic_name(doc.text)
            brand_names = self._extract_brand_names(doc.text)
            drug_class = self._extract_drug_class(doc.text)
            common_uses = self._extract_common_uses(doc.text)
            
            # Get feedback counts for this drug and query
            feedback_counts = self.get_feedback_counts(drug_name, query)
            
            # Store original name for dosage extraction
            original_name = doc.title
            
            return DrugSearchResult(
                rxcui=doc.rxcui,
                name=drug_name,
                generic_name=generic_name,
                brand_names=brand_names,
                common_uses=common_uses,
                drug_class=drug_class,
                source=doc.source.value,
                helpful_count=feedback_counts["helpful"],
                not_helpful_count=feedback_counts["not_helpful"],
                original_name=original_name,  # Store original name for dosage extraction
                all_rxcuis=[doc.rxcui] if doc.rxcui else []  # Single RxCUI for non-combined results
            )
        except Exception as e:
            logger.error(f"Error converting doc to DrugSearchResult: {str(e)}")
            return None
    
    def _is_invalid_drug_name(self, name: str) -> bool:
        """Check if the drug name is invalid or not a real drug."""
        if not name:
            return True
        
        name_lower = name.lower()
        
        # Filter out database references and non-drug entries
        invalid_patterns = [
            'adverse event',
            'drugbank:',
            'rxnorm:',
            'dailymed:',
            'openfda:',
            'einjection',
            'injection injection',  # Duplicate injection
            'clinimix',  # This is a parenteral nutrition, not an oral medication
        ]
        
        for pattern in invalid_patterns:
            if pattern in name_lower:
                return True
        
        # Filter out very short names that are likely not drugs
        if len(name.strip()) < 3:
            return True
        
        # Filter out names that are just numbers or special characters
        if re.match(r'^[\d\s\-_\.]+$', name):
            return True
        
        return False
    
    def _clean_drug_name(self, name: str) -> str:
        """Clean and standardize drug name."""
        if not name:
            return name
        
        # Remove common prefixes and suffixes that aren't part of the drug name
        name = name.strip()
        
        # Fix common typos and duplicates
        import re
        name = re.sub(r'\b(einjection)\b', 'injection', name, flags=re.IGNORECASE)
        
        # Remove duplicate words (like "Clinimix Einjection Clinimix Einjection")
        words = name.split()
        seen = set()
        unique_words = []
        for word in words:
            if word.lower() not in seen:
                seen.add(word.lower())
                unique_words.append(word)
        name = ' '.join(unique_words)
        
        # Remove dosage information and extended release info
        name = re.sub(r'\s+\d+\s*(mg|mcg|g|ml|%|mg/ml|mcg/ml)\s*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\d+\s*HR\s*', ' ', name, flags=re.IGNORECASE)  # Remove "24 HR" etc.
        name = re.sub(r'\s+Extended\s+Release\s*', ' ', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+hydrochloride\s*', ' ', name, flags=re.IGNORECASE)  # Remove hydrochloride
        name = re.sub(r'\s+sulfate\s*', ' ', name, flags=re.IGNORECASE)  # Remove sulfate
        name = re.sub(r'\s+acetate\s*', ' ', name, flags=re.IGNORECASE)  # Remove acetate
        
        # Remove common medication type suffixes
        name = re.sub(r'\s+(tablet|capsule|solution|cream|gel|patch|drops|spray|inhaler|syrup|suspension|powder|oral|topical|injection)\s*$', '', name, flags=re.IGNORECASE)
        
        # Remove bracketed information
        name = re.sub(r'\s*\[.*?\]\s*', '', name)
        name = re.sub(r'\s*\(.*?\)\s*', '', name)
        
        # Extract the main drug name (usually the first part before "/")
        if '/' in name:
            name = name.split('/')[0].strip()
        
        # Clean up extra spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        # If the name is still very long, try to extract just the main drug name
        if len(name) > 50:
            # Look for common drug name patterns
            drug_patterns = [
                r'\b(metformin|atorvastatin|simvastatin|lisinopril|amlodipine|omeprazole|metoprolol|acetaminophen|ibuprofen|naproxen|tramadol|warfarin|apixaban|amoxicillin|azithromycin|ciprofloxacin|penicillin)\b',
                r'\b([A-Z][a-z]+(?:mycin|statin|pril|sartan|pine|zole|mide|pam|zine|formin|olol))\b',
            ]
            
            for pattern in drug_patterns:
                matches = re.findall(pattern, name, re.IGNORECASE)
                if matches:
                    return matches[0].title()
        
        # Properly capitalize the drug name
        return self._properly_capitalize_drug_name(name)
    
    def _properly_capitalize_drug_name(self, name: str) -> str:
        """Properly capitalize drug names."""
        if not name:
            return name
        
        # Common drug name patterns that should be capitalized properly
        drug_capitalization = {
            'acetaminophen': 'Acetaminophen',
            'metformin': 'Metformin',
            'atorvastatin': 'Atorvastatin',
            'simvastatin': 'Simvastatin',
            'lisinopril': 'Lisinopril',
            'amlodipine': 'Amlodipine',
            'omeprazole': 'Omeprazole',
            'metoprolol': 'Metoprolol',
            'ibuprofen': 'Ibuprofen',
            'naproxen': 'Naproxen',
            'tramadol': 'Tramadol',
            'warfarin': 'Warfarin',
            'apixaban': 'Apixaban',
            'amoxicillin': 'Amoxicillin',
            'azithromycin': 'Azithromycin',
            'ciprofloxacin': 'Ciprofloxacin',
            'penicillin': 'Penicillin',
            'methionine': 'Methionine',
            'alanine': 'Alanine',
            'arginine': 'Arginine',
        }
        
        name_lower = name.lower()
        if name_lower in drug_capitalization:
            return drug_capitalization[name_lower]
        
        # For other names, use title case but handle special cases
        import re
        # Handle camelCase like "methionineOral"
        if re.match(r'^[a-z]+[A-Z]', name):
            # Split camelCase
            words = re.findall(r'[a-z]+|[A-Z][a-z]*', name)
            return ' '.join(word.capitalize() for word in words)
        
        # Standard title case
        return name.title()
    
    def _extract_drug_name(self, text: str) -> Optional[str]:
        """Extract drug name from text."""
        if not text:
            return None
        
        # First, try to extract from title if available
        if hasattr(self, '_current_doc_title') and self._current_doc_title:
            title = self._current_doc_title
            # Look for drug names in title
            drug_name = self._extract_drug_from_title(title)
            if drug_name:
                return drug_name
        
        # Look for common drug name patterns in text
        patterns = [
            # Common drug suffixes
            r'\b([A-Z][a-z]+(?:mycin|statin|pril|sartan|pine|zole|mide|pam|zine|formin|olol|sartan|pril|pine|zole))\b',
            r'\b([A-Z][a-z]+(?:cillin|cycline|floxacin|mycin|bicin|micin))\b',
            r'\b([A-Z][a-z]+(?:olol|sartan|pril|pine|zole|dipine|zosin))\b',
            # Common drug prefixes
            r'\b(metformin|atorvastatin|simvastatin|lisinopril|amlodipine|omeprazole|metoprolol)\b',
            r'\b(acetaminophen|ibuprofen|naproxen|tramadol|warfarin|apixaban)\b',
            r'\b(amoxicillin|azithromycin|ciprofloxacin|doxycycline|penicillin)\b',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0].title()
        
        # Look for drug names in common medical text patterns
        medical_patterns = [
            r'drug\s+name[:\s]+([A-Z][a-z]+)',
            r'medication[:\s]+([A-Z][a-z]+)',
            r'generic\s+name[:\s]+([A-Z][a-z]+)',
            r'active\s+ingredient[:\s]+([A-Z][a-z]+)',
        ]
        
        for pattern in medical_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        
        # Fallback: look for capitalized words that might be drug names
        # But exclude common medical terms
        words = re.findall(r'\b[A-Z][a-z]{3,}\b', text)
        exclude_words = {
            'the', 'and', 'for', 'with', 'from', 'this', 'that', 'oral', 'adverse', 
            'effect', 'side', 'drug', 'medication', 'tablet', 'capsule', 'dose',
            'dosage', 'mg', 'mcg', 'ml', 'solution', 'injection', 'cream', 'gel',
            'patch', 'drops', 'spray', 'inhaler', 'syrup', 'suspension', 'powder',
            'treatment', 'therapy', 'patient', 'doctor', 'physician', 'nurse',
            'hospital', 'clinic', 'pharmacy', 'prescription', 'prescribed'
        }
        
        for word in words:
            if word.lower() not in exclude_words:
                return word
        
        return None
    
    def _extract_drug_from_title(self, title: str) -> Optional[str]:
        """Extract drug name from document title."""
        if not title:
            return None
        
        # Common patterns in medical document titles
        patterns = [
            r'^([A-Z][a-z]+)\s+',  # First word if capitalized
            r'([A-Z][a-z]+(?:mycin|statin|pril|sartan|pine|zole|mide|pam|zine|formin|olol))\b',
            r'([A-Z][a-z]+(?:cillin|cycline|floxacin|mycin|bicin|micin))\b',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, title)
            if matches:
                return matches[0]
        
        return None
    
    def _extract_generic_name(self, text: str) -> Optional[str]:
        """Extract generic name from text."""
        # Look for patterns like "generic name: X" or "also known as X"
        patterns = [
            r'generic\s+name[:\s]+([A-Z][a-z]+)',
            r'also\s+known\s+as[:\s]+([A-Z][a-z]+)',
            r'generic[:\s]+([A-Z][a-z]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return None
    
    def _extract_brand_names(self, text: str) -> List[str]:
        """Extract brand names from text."""
        brand_names = []
        
        # Look for patterns like "brand names: X, Y, Z"
        patterns = [
            r'brand\s+names?[:\s]+([^.]+)',
            r'trade\s+names?[:\s]+([^.]+)',
            r'commercial\s+names?[:\s]+([^.]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Split by common separators
                names = re.split(r'[,;]', matches[0])
                brand_names.extend([name.strip() for name in names if name.strip()])
        
        return brand_names[:5]  # Limit to 5 brand names
    
    def _extract_drug_class(self, text: str) -> Optional[str]:
        """Extract drug class from text."""
        # Common drug classes
        drug_classes = [
            'statin', 'beta blocker', 'ace inhibitor', 'arb', 'calcium channel blocker',
            'ppi', 'h2 blocker', 'nsaid', 'opioid', 'antibiotic', 'anticoagulant',
            'antihistamine', 'antidepressant', 'antipsychotic', 'diuretic'
        ]
        
        text_lower = text.lower()
        for drug_class in drug_classes:
            if drug_class in text_lower:
                return drug_class.title()
        
        return None
    
    def _extract_common_uses(self, text: str) -> List[str]:
        """Extract common uses from text."""
        uses = []
        
        # Look for indication patterns with better text cleaning
        patterns = [
            r'used\s+to\s+treat[:\s]+([^.]+)',
            r'indicated\s+for[:\s]+([^.]+)',
            r'treatment\s+of[:\s]+([^.]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Split by common separators and clean each use
                indications = re.split(r'[,;]', matches[0])
                for ind in indications:
                    cleaned = ind.strip()
                    # Limit length and clean up formatting
                    if len(cleaned) > 100:
                        cleaned = cleaned[:100] + "..."
                    # Remove excessive whitespace and newlines
                    cleaned = re.sub(r'\s+', ' ', cleaned)
                    if cleaned and len(cleaned) > 3:
                        uses.append(cleaned)
        
        # If no uses found or uses are too long, add common uses based on drug name
        if not uses or any(len(use) > 50 for use in uses):
            uses = self._get_common_uses_by_drug_name(text)
        
        return uses[:3]  # Limit to 3 common uses
    
    def _get_common_uses_by_drug_name(self, text: str) -> List[str]:
        """Get common uses based on drug name patterns."""
        text_lower = text.lower()
        
        # Common drug uses mapping - more comprehensive
        drug_uses = {
            # Pain medications
            'acetaminophen': ['Pain relief', 'Fever reduction'],
            'ibuprofen': ['Pain relief', 'Inflammation', 'Fever reduction'],
            'naproxen': ['Pain relief', 'Inflammation', 'Arthritis'],
            'tramadol': ['Pain relief', 'Moderate to severe pain'],
            'gabapentin': ['Nerve pain', 'Seizures', 'Neuropathic pain'],
            'pregabalin': ['Nerve pain', 'Fibromyalgia', 'Neuropathic pain'],
            
            # Diabetes medications
            'metformin': ['Type 2 diabetes', 'Blood sugar control'],
            'glipizide': ['Type 2 diabetes', 'Blood sugar control'],
            'insulin': ['Diabetes', 'Blood sugar control'],
            
            # Cholesterol medications
            'atorvastatin': ['High cholesterol', 'Heart disease prevention'],
            'simvastatin': ['High cholesterol', 'Heart disease prevention'],
            'rosuvastatin': ['High cholesterol', 'Heart disease prevention'],
            'pravastatin': ['High cholesterol', 'Heart disease prevention'],
            'ezetimibe': ['High cholesterol', 'Cholesterol absorption'],
            
            # Blood pressure medications
            'lisinopril': ['High blood pressure', 'Heart failure'],
            'amlodipine': ['High blood pressure', 'Chest pain'],
            'metoprolol': ['High blood pressure', 'Heart rhythm disorders'],
            'losartan': ['High blood pressure', 'Heart failure'],
            'valsartan': ['High blood pressure', 'Heart failure'],
            
            # Heart medications
            'warfarin': ['Blood thinning', 'Prevent blood clots'],
            'apixaban': ['Blood thinning', 'Prevent stroke'],
            'rivaroxaban': ['Blood thinning', 'Prevent stroke'],
            'clopidogrel': ['Blood thinning', 'Prevent heart attack'],
            
            # Stomach medications
            'omeprazole': ['Acid reflux', 'Stomach ulcers'],
            'pantoprazole': ['Acid reflux', 'Stomach ulcers'],
            'ranitidine': ['Acid reflux', 'Stomach ulcers'],
            
            # Antibiotics
            'amoxicillin': ['Bacterial infections', 'Respiratory infections'],
            'azithromycin': ['Bacterial infections', 'Respiratory infections'],
            'ciprofloxacin': ['Bacterial infections', 'Urinary tract infections'],
            'penicillin': ['Bacterial infections', 'Respiratory infections'],
            'doxycycline': ['Bacterial infections', 'Acne'],
            
            # Supplements
            'methionine': ['Liver support', 'Amino acid supplement'],
            'alanine': ['Amino acid supplement', 'Protein synthesis'],
            'arginine': ['Heart health', 'Blood vessel function'],
            
            # Other common medications
            'levothyroxine': ['Hypothyroidism', 'Thyroid hormone replacement'],
            'prednisone': ['Inflammation', 'Autoimmune conditions'],
            'hydrocodone': ['Pain relief', 'Cough suppression'],
            'oxycodone': ['Pain relief', 'Severe pain'],
        }
        
        # Check for drug names in text (more flexible matching)
        for drug_name, uses in drug_uses.items():
            # Check if drug name appears in the text
            if drug_name in text_lower:
                return uses
            
            # Also check for partial matches (e.g., "atorvastatin" in "atorvastatin calcium")
            if any(word.startswith(drug_name) for word in text_lower.split()):
                return uses
        
        return []
    
    def _combine_duplicate_drugs(self, results: List[DrugSearchResult]) -> List[DrugSearchResult]:
        """Combine duplicate drugs with different dosages into single results."""
        if not results:
            return results
        
        # Group results by base drug name (remove dosage info for grouping)
        drug_groups = {}
        for result in results:
            base_name = self._get_base_drug_name(result.name)
            if base_name not in drug_groups:
                drug_groups[base_name] = []
            drug_groups[base_name].append(result)
        
        # Combine groups with multiple entries
        combined_results = []
        for base_name, group in drug_groups.items():
            if len(group) == 1:
                # Single result, keep as is
                combined_results.append(group[0])
            else:
                # Multiple results, combine them
                combined_result = self._merge_drug_results(group)
                combined_results.append(combined_result)
        
        return combined_results
    
    def _get_base_drug_name(self, name: str) -> str:
        """Get base drug name without dosage information for grouping."""
        import re
        
        # Remove dosage information (including decimal numbers)
        base_name = re.sub(r'\s+\d+\.?\d*\s*(mg|mcg|g|ml|%|mg/ml|mcg/ml)\s*', '', name, flags=re.IGNORECASE)
        base_name = re.sub(r'\s*\d+\.?\d*\s*HR\s*', ' ', base_name, flags=re.IGNORECASE)
        base_name = re.sub(r'\s+Extended\s+Release\s*', ' ', base_name, flags=re.IGNORECASE)
        
        # Remove common medication type suffixes
        base_name = re.sub(r'\s+(tablet|capsule|solution|cream|gel|patch|drops|spray|inhaler|syrup|suspension|powder|oral|topical|injection)\s*$', '', base_name, flags=re.IGNORECASE)
        
        # Remove extra words that might be concatenated
        base_name = re.sub(r'(oral|tablet|capsule)$', '', base_name, flags=re.IGNORECASE)
        
        # Clean up extra spaces and special characters
        base_name = re.sub(r'\s+', ' ', base_name).strip()
        base_name = re.sub(r'[,\-\.]+$', '', base_name)  # Remove trailing punctuation
        
        return base_name.lower()
    
    def _merge_drug_results(self, results: List[DrugSearchResult]) -> DrugSearchResult:
        """Merge multiple drug results into a single result with dosage information."""
        if not results:
            return None
        
        # Use the first result as the base
        base_result = results[0]
        
        # Collect all RxCUIs
        all_rxcuis = [result.rxcui for result in results if result.rxcui]
        primary_rxcui = all_rxcuis[0] if all_rxcuis else base_result.rxcui
        all_rxcui_list = list(dict.fromkeys(all_rxcuis))  # Remove duplicates while preserving order
        
        # Collect all brand names
        all_brand_names = []
        for result in results:
            if result.brand_names:
                all_brand_names.extend(result.brand_names)
        
        # Remove duplicates and keep unique brand names
        unique_brand_names = list(dict.fromkeys(all_brand_names))
        
        # Use the most complete common uses
        best_common_uses = []
        for result in results:
            if result.common_uses and len(result.common_uses) > len(best_common_uses):
                best_common_uses = result.common_uses
        
        # Use the most specific drug class
        best_drug_class = None
        for result in results:
            if result.drug_class and result.drug_class != 'Medication':
                best_drug_class = result.drug_class
                break
        
        # Extract dosage information from all results
        dosages = self._extract_dosages_from_results(results)
        
        # Create a more descriptive name that includes dosage info
        base_name = self._get_base_drug_name(base_result.name)
        if dosages:
            # Create a name like "Glipizide (1mg, 2.5mg, 5mg)"
            dosage_str = ", ".join(dosages)
            display_name = f"{base_name.title()} ({dosage_str})"
        else:
            display_name = base_name.title()
        
        # Create merged result
        merged_result = DrugSearchResult(
            rxcui=primary_rxcui,
            name=display_name,
            generic_name=base_result.generic_name,
            brand_names=unique_brand_names[:5],  # Limit to 5 brand names
            common_uses=best_common_uses,
            drug_class=best_drug_class or base_result.drug_class,
            source=base_result.source,
            helpful_count=base_result.helpful_count,
            not_helpful_count=base_result.not_helpful_count,
            all_rxcuis=all_rxcui_list  # Include all RxCUIs
        )
        
        return merged_result
    
    def _extract_dosages_from_results(self, results: List[DrugSearchResult]) -> List[str]:
        """Extract dosage information from multiple drug results."""
        dosages = []
        
        for result in results:
            # Extract dosage from the original name if available, otherwise from current name
            original_name = getattr(result, 'original_name', result.name)
            dosage = self._extract_dosage_from_name(original_name)
            if dosage and dosage not in dosages:
                dosages.append(dosage)
        
        # Sort dosages numerically for better display
        return self._sort_dosages(dosages)
    
    def _extract_dosage_from_name(self, name: str) -> Optional[str]:
        """Extract dosage information from drug name."""
        import re
        
        # Look for dosage patterns like "2.5mg", "10mg", "500mcg", etc.
        dosage_patterns = [
            r'(\d+\.?\d*)\s*(mg|mcg|g|ml|%|mg/ml|mcg/ml)',
            r'(\d+\.?\d*)\s*HR',  # Extended release like "24 HR"
        ]
        
        for pattern in dosage_patterns:
            matches = re.findall(pattern, name, re.IGNORECASE)
            if matches:
                # Return the first dosage found
                dosage_value, unit = matches[0]
                return f"{dosage_value}{unit.lower()}"
        
        return None
    
    def _sort_dosages(self, dosages: List[str]) -> List[str]:
        """Sort dosages numerically for better display."""
        if not dosages:
            return dosages
        
        def dosage_sort_key(dosage: str) -> float:
            """Extract numeric value for sorting."""
            import re
            match = re.match(r'(\d+\.?\d*)', dosage)
            if match:
                return float(match.group(1))
            return 0.0
        
        return sorted(dosages, key=dosage_sort_key)
    
    def _filter_oral_medications(self, results: List[DrugSearchResult]) -> List[DrugSearchResult]:
        """Filter results to focus on oral medications only."""
        filtered_results = []
        
        for result in results:
            # Check if this is likely an oral medication
            if self._is_oral_medication(result):
                filtered_results.append(result)
        
        return filtered_results
    
    def _is_oral_medication(self, result: DrugSearchResult) -> bool:
        """Check if a medication is likely oral."""
        # Check name and description for oral medication indicators
        text_to_check = f"{result.name} {result.generic_name} {' '.join(result.brand_names or [])}"
        text_lower = text_to_check.lower()
        
        # Exclude non-oral medications
        for exclude_pattern in self._exclude_patterns:
            if re.search(exclude_pattern, text_lower):
                return False
        
        # Include if it matches discharge medication patterns
        for include_pattern in self._discharge_med_patterns:
            if re.search(include_pattern, text_lower):
                return True
        
        # Default to include if no exclusion patterns match
        return True
    
    async def _enhance_with_vector_search(self, query: str, results: List[DrugSearchResult]) -> List[DrugSearchResult]:
        """Enhance results with vector search for additional context."""
        try:
            # Only use vector search if we have few results or need enhancement
            if len(results) >= 3:
                # Skip vector search to reduce API calls when we have good results
                return results
            
            # Generate embedding for the query (cached)
            query_embedding = (await embed([query]))[0]
            
            # Search vector database
            vector_results = search_vector(query_embedding, limit=3)  # Reduced limit
            
            # Enhance existing results with vector search context
            enhanced_results = []
            for result in results:
                # Find matching vector results
                matching_vectors = [vr for vr in vector_results if 
                                  result.name.lower() in vr['text'].lower() or
                                  (result.generic_name and result.generic_name.lower() in vr['text'].lower())]
                
                if matching_vectors:
                    # Enhance with vector search information
                    vector_info = matching_vectors[0]
                    if not result.common_uses:
                        result.common_uses = self._extract_common_uses(vector_info['text'])
                    if not result.drug_class:
                        result.drug_class = self._extract_drug_class(vector_info['text'])
                
                enhanced_results.append(result)
            
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Error in vector search enhancement: {str(e)}")
            return results
    
    def _apply_feedback_scoring(self, results: List[DrugSearchResult], query: str) -> List[DrugSearchResult]:
        """Apply ML feedback scoring to results."""
        for result in results:
            # Get feedback counts for this drug-query combination
            feedback_counts = self.get_feedback_counts(result.name, query)
            
            # Calculate feedback score from counts (helpful vs not_helpful ratio)
            total_votes = feedback_counts["helpful"] + feedback_counts["not_helpful"]
            if total_votes > 0:
                result.feedback_score = feedback_counts["helpful"] / total_votes
            else:
                result.feedback_score = 0.5  # Neutral score if no feedback
            
            # Calculate discharge relevance score based on feedback and drug patterns
            result.discharge_relevance_score = self._calculate_discharge_relevance(result, query)
        
        return results
    
    def _calculate_discharge_relevance(self, result: DrugSearchResult, query: str) -> float:
        """Calculate discharge relevance score based on feedback and patterns."""
        base_score = 0.5
        
        # Boost for common discharge medications
        if any(re.search(pattern, result.name.lower()) for pattern in self._discharge_med_patterns):
            base_score += 0.2
        
        # Boost for positive feedback
        if result.feedback_score > 0.5:
            base_score += (result.feedback_score - 0.5) * 0.3
        
        # Penalty for negative feedback
        if result.feedback_score < 0.5:
            base_score -= (0.5 - result.feedback_score) * 0.2
        
        # Boost for exact name matches
        if result.name.lower() == query.lower():
            base_score += 0.1
        
        # Boost for name starts with query
        if result.name.lower().startswith(query.lower()):
            base_score += 0.05
        
        # Ensure score is between 0 and 1
        return max(0.0, min(1.0, base_score))
    
    def _sort_by_discharge_relevance(self, results: List[DrugSearchResult], query: str) -> List[DrugSearchResult]:
        """Sort results by relevance to post-discharge medications."""
        def relevance_score(result: DrugSearchResult) -> float:
            # Use the calculated discharge relevance score
            return getattr(result, 'discharge_relevance_score', 0.5)
        
        return sorted(results, key=relevance_score, reverse=True)
    
    def _filter_ignored_medications(self, results: List[DrugSearchResult], query: str) -> List[DrugSearchResult]:
        """Filter out medications that have been marked as ignored based on feedback."""
        filtered_results = []
        
        for result in results:
            # Check if this medication should be ignored
            if self._feedback_db.is_medication_ignored(result.name, query):
                logger.info(f"Filtering out ignored medication: {result.name} for query: {query}")
                continue
            
            filtered_results.append(result)
        
        logger.info(f"Filtered {len(results) - len(filtered_results)} ignored medications from {len(results)} total results")
        return filtered_results
    
    def record_feedback(self, drug_name: str, query: str, is_positive: bool, is_removal: bool = False):
        """Record user feedback for ML pipeline."""
        return self._feedback_db.record_feedback(drug_name, query, is_positive, is_removal=is_removal)
    
    def get_feedback_counts(self, drug_name: str, query: str) -> Dict[str, int]:
        """Get feedback counts for a specific drug and query."""
        return self._feedback_db.get_feedback_counts(drug_name, query)

# Global instance
_post_discharge_search_service = None

async def get_post_discharge_search_service() -> PostDischargeSearchService:
    """Get the global post-discharge search service instance."""
    global _post_discharge_search_service
    if _post_discharge_search_service is None:
        _post_discharge_search_service = PostDischargeSearchService()
    return _post_discharge_search_service
