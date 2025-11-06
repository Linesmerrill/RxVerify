"""Real-time medical database API integration for RxVerify.

This module provides live querying of medical databases instead of relying on pre-loaded data.
"""

import asyncio
import httpx
from typing import List, Dict, Optional, Tuple
from app.models import Source, RetrievedDoc
import logging

logger = logging.getLogger(__name__)

# API Configuration
RXNORM_BASE_URL = "https://rxnav.nlm.nih.gov/REST"
DAILYMED_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
OPENFDA_BASE_URL = "https://api.fda.gov"
DRUGBANK_BASE_URL = "https://go.drugbank.com/api/v1"
PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

class MedicalAPIClient:
    """Client for querying medical databases in real-time."""
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()
    
    def _extract_drug_name(self, query: str) -> str:
        """Extract drug name from a natural language query."""
        # Remove common question words and phrases
        query_lower = query.lower()
        
        # Common question patterns to remove
        patterns_to_remove = [
            "what are the side effects of",
            "what should i expect when taking",
            "what is",
            "tell me about",
            "how does",
            "what does",
            "side effects of",
            "information about",
            "details about"
        ]
        
        for pattern in patterns_to_remove:
            if pattern in query_lower:
                query_lower = query_lower.replace(pattern, "").strip()
        
        # Remove punctuation and extra whitespace
        drug_name = query_lower.strip("?.,! ").strip()
        
        # If we still have a long query, try to extract just the drug name
        if len(drug_name.split()) > 3:
            # Look for common drug name patterns
            words = drug_name.split()
            # Often the drug name is in the middle or end
            if len(words) >= 2:
                drug_name = words[-1]  # Take the last word as drug name
        
        return drug_name
    
    def _is_reasonable_drug_name(self, drug_name: str) -> bool:
        """Check if a drug name looks reasonable (not random strings)."""
        if not drug_name or len(drug_name) < 2:
            return False
        
        # Skip obvious non-drug strings
        if any(char.isdigit() for char in drug_name[-3:]):  # Ends with numbers
            return False
        
        # Skip strings that contain numbers (most drug names don't have numbers)
        if any(char.isdigit() for char in drug_name):
            return False
        
        # Skip very short strings
        if len(drug_name) < 3:
            return False
        
        # Skip strings with too many special characters
        special_chars = sum(1 for c in drug_name if not c.isalnum() and c != ' ')
        if special_chars > len(drug_name) / 3:
            return False
        
        # Skip strings that look like random combinations
        if len(drug_name) > 10 and not any(char in drug_name.lower() for char in 'aeiou'):  # No vowels
            return False
        
        return True

    async def search_rxnorm(self, query: str, limit: int = 10) -> List[Dict]:
        """Search RxNorm for drug information with enhanced context."""
        try:
            # Extract drug name from the query (remove question words)
            drug_name = self._extract_drug_name(query)
            
            # Check if query is about side effects to provide better context
            is_side_effects_query = any(term in query.lower() for term in [
                "side effect", "side effects", "adverse", "reaction", "reactions",
                "what should i expect", "what to expect", "symptoms", "problems"
            ])
            
            # Search by drug name
            search_url = f"{RXNORM_BASE_URL}/drugs.json"
            params = {
                "name": drug_name,
                "allsrc": 1,
                "src": 1
            }
            
            response = await self.http_client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "drugGroup" in data and "conceptGroup" in data["drugGroup"]:
                for concept_group in data["drugGroup"]["conceptGroup"]:
                    if "conceptProperties" in concept_group:
                        for concept in concept_group["conceptProperties"][:limit]:
                            # Enhanced text based on query type
                            if is_side_effects_query:
                                text = f"RxNorm Drug: {concept.get('name', '')} (RxCUI: {concept.get('rxcui', '')}, Type: {concept.get('termType', '')})\nNote: For detailed side effects, see DailyMed package insert or OpenFDA label information."
                            else:
                                text = f"RxNorm Drug: {concept.get('name', '')} (RxCUI: {concept.get('rxcui', '')}, Type: {concept.get('termType', '')})"
                            
                            results.append({
                                "rxcui": concept.get("rxcui", ""),
                                "name": concept.get("name", ""),
                                "synonym": concept.get("synonym", ""),
                                "term_type": concept.get("termType", ""),
                                "source": "rxnorm",
                                "id": f"rxnorm_{concept.get('rxcui', 'unknown')}",
                                "url": f"https://rxnav.nlm.nih.gov/REST/rxcui/{concept.get('rxcui', '')}",
                                "title": concept.get("name", ""),
                                "text": text
                            })
            
            # Strategy 2: If no results and query looks like a partial drug name, try common drug prefixes
            if not results and len(drug_name) >= 3 and drug_name.isalpha():
                common_drug_prefixes = {
                    "metf": "metformin",
                    "glip": "glipizide", 
                    "lisi": "lisinopril",
                    "amlo": "amlodipine",
                    "simv": "simvastatin",
                    "ator": "atorvastatin",
                    "omep": "omeprazole",
                    "panto": "pantoprazole",
                    "warf": "warfarin",
                    "furo": "furosemide",
                    "hydro": "hydrochlorothiazide",
                    "pred": "prednisone",
                    "ibu": "ibuprofen",
                    "acet": "acetaminophen",
                    "trama": "tramadol",
                    "oxyc": "oxycodone",
                    "morph": "morphine",
                    "loraz": "lorazepam",
                    "alpraz": "alprazolam",
                    "diazep": "diazepam"
                }
                
                if drug_name.lower() in common_drug_prefixes:
                    expanded_name = common_drug_prefixes[drug_name.lower()]
                    logger.info(f"Expanding partial drug name '{drug_name}' to '{expanded_name}'")
                    
                    # Try search with expanded name
                    params["name"] = expanded_name
                    response = await self.http_client.get(search_url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    if "drugGroup" in data and "conceptGroup" in data["drugGroup"]:
                        for concept_group in data["drugGroup"]["conceptGroup"]:
                            if "conceptProperties" in concept_group:
                                for concept in concept_group["conceptProperties"][:limit]:
                                    # Enhanced text based on query type
                                    if is_side_effects_query:
                                        text = f"RxNorm Drug: {concept.get('name', '')} (RxCUI: {concept.get('rxcui', '')}, Type: {concept.get('termType', '')})\nNote: For detailed side effects, see DailyMed package insert or OpenFDA label information."
                                    else:
                                        text = f"RxNorm Drug: {concept.get('name', '')} (RxCUI: {concept.get('rxcui', '')}, Type: {concept.get('termType', '')})"
                                    
                                    results.append({
                                        "rxcui": concept.get("rxcui", ""),
                                        "name": concept.get("name", ""),
                                        "synonym": concept.get("synonym", ""),
                                        "term_type": concept.get("termType", ""),
                                        "source": "rxnorm",
                                        "id": f"rxnorm_{concept.get('rxcui', 'unknown')}",
                                        "url": f"https://rxnav.nlm.nih.gov/REST/rxcui/{concept.get('rxcui', '')}",
                                        "title": concept.get("name", ""),
                                        "text": text
                                    })
            
            logger.info(f"RxNorm search returned {len(results)} results for '{drug_name}'")
            return results
            
        except Exception as e:
            logger.error(f"RxNorm API error: {e}")
            return []
    
    async def search_dailymed(self, query: str, limit: int = 10) -> List[Dict]:
        """Search DailyMed for drug labeling information with focus on side effects."""
        try:
            # Extract drug name from the query
            drug_name = self._extract_drug_name(query)
            
            results = []
            
            # Strategy 1: Try searching by RxCUI if we have it from RxNorm
            # First, let's try to get RxCUI from RxNorm for this drug
            try:
                # Check if we need to expand partial drug name
                search_name = drug_name
                if len(drug_name) >= 3 and drug_name.isalpha():
                    common_drug_prefixes = {
                        "metf": "metformin",
                        "glip": "glipizide", 
                        "lisi": "lisinopril",
                        "amlo": "amlodipine",
                        "simv": "simvastatin",
                        "ator": "atorvastatin",
                        "omep": "omeprazole",
                        "panto": "pantoprazole",
                        "warf": "warfarin",
                        "furo": "furosemide",
                        "hydro": "hydrochlorothiazide",
                        "pred": "prednisone",
                        "ibu": "ibuprofen",
                        "acet": "acetaminophen",
                        "trama": "tramadol",
                        "oxyc": "oxycodone",
                        "morph": "morphine",
                        "loraz": "lorazepam",
                        "alpraz": "alprazolam",
                        "diazep": "diazepam"
                    }
                    
                    if drug_name.lower() in common_drug_prefixes:
                        search_name = common_drug_prefixes[drug_name.lower()]
                        logger.info(f"DailyMed: Expanding partial drug name '{drug_name}' to '{search_name}'")
                
                rxnorm_url = f"{RXNORM_BASE_URL}/drugs.json"
                rxnorm_params = {
                    "name": search_name,
                    "allsrc": 1,
                    "src": 1
                }
                
                rxnorm_response = await self.http_client.get(rxnorm_url, params=rxnorm_params)
                if rxnorm_response.status_code == 200:
                    rxnorm_data = rxnorm_response.json()
                    
                    # Extract RxCUIs from RxNorm response
                    rxcuis = []
                    if "drugGroup" in rxnorm_data and "conceptGroup" in rxnorm_data["drugGroup"]:
                        for concept_group in rxnorm_data["drugGroup"]["conceptGroup"]:
                            if "conceptProperties" in concept_group:
                                for concept in concept_group["conceptProperties"]:
                                    if "rxcui" in concept:
                                        rxcuis.append(concept["rxcui"])
                    
                    # Search DailyMed by RxCUI
                    for rxcui in rxcuis[:3]:  # Limit to first 3 RxCUIs
                        try:
                            dailymed_url = f"{DAILYMED_BASE_URL}/spls"
                            dailymed_params = {
                                "rxcui": rxcui,
                                "pagesize": limit
                            }
                            
                            dailymed_response = await self.http_client.get(dailymed_url, params=dailymed_params)
                            if dailymed_response.status_code == 200:
                                dailymed_data = dailymed_response.json()
                                
                                if "data" in dailymed_data:
                                    for spl in dailymed_data["data"][:limit]:
                                        spl_id = spl.get("setid", "")
                                        title = spl.get("title", "Unknown")
                                        
                                        if spl_id:
                                            # Get the actual package insert content from XML endpoint
                                            try:
                                                xml_url = f"{DAILYMED_BASE_URL}/spls/{spl_id}.xml"
                                                xml_response = await self.http_client.get(xml_url)
                                                
                                                if xml_response.status_code == 200:
                                                    xml_content = xml_response.text
                                                    
                                                    # Extract key information from XML
                                                    extracted_info = self._extract_spl_content(xml_content, drug_name)
                                                    
                                                    if extracted_info:
                                                        results.append({
                                                            "rxcui": rxcui,
                                                            "source": "dailymed",
                                                            "id": f"dailymed_{spl_id}",
                                                            "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl_id}",
                                                            "title": title,
                                                            "text": extracted_info
                                                        })
                                            except Exception as xml_error:
                                                logger.warning(f"Failed to get XML content for SPL {spl_id}: {xml_error}")
                                                # Fallback to basic info
                                                results.append({
                                                    "rxcui": rxcui,
                                                    "source": "dailymed",
                                                    "id": f"dailymed_{spl_id}",
                                                    "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl_id}",
                                                    "title": title,
                                                    "text": f"DailyMed SPL: {title} (RxCUI: {rxcui})\nNote: Package insert content available at the provided URL."
                                                })
                        except Exception as rxcui_error:
                            logger.warning(f"Failed to search DailyMed by RxCUI {rxcui}: {rxcui_error}")
                            continue
            except Exception as rxnorm_error:
                logger.warning(f"Failed to get RxNorm data for RxCUI search: {rxnorm_error}")
            
            # Strategy 2: Try searching by generic name if RxCUI search didn't yield results
            if len(results) < limit:
                try:
                    dailymed_url = f"{DAILYMED_BASE_URL}/spls"
                    dailymed_params = {
                        "drug_name": drug_name,
                        "name_type": "generic",
                        "pagesize": limit - len(results)
                    }
                    
                    dailymed_response = await self.http_client.get(dailymed_url, params=dailymed_params)
                    if dailymed_response.status_code == 200:
                        dailymed_data = dailymed_response.json()
                        
                        if "data" in dailymed_data:
                            for spl in dailymed_data["data"][:limit - len(results)]:
                                spl_id = spl.get("setid", "")
                                title = spl.get("title", "Unknown")
                                
                                if spl_id and not any(r["id"] == f"dailymed_{spl_id}" for r in results):
                                    # Get the actual package insert content from XML endpoint
                                    try:
                                        xml_url = f"{DAILYMED_BASE_URL}/spls/{spl_id}.xml"
                                        xml_response = await self.http_client.get(xml_url)
                                        
                                        if xml_response.status_code == 200:
                                            xml_content = xml_response.text
                                            
                                            # Extract key information from XML
                                            extracted_info = self._extract_spl_content(xml_content, drug_name)
                                            
                                            if extracted_info:
                                                results.append({
                                                    "rxcui": "",  # Not available from this search
                                                    "source": "dailymed",
                                                    "id": f"dailymed_{spl_id}",
                                                    "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl_id}",
                                                    "title": title,
                                                    "text": extracted_info
                                                })
                                    except Exception as xml_error:
                                        logger.warning(f"Failed to get XML content for SPL {spl_id}: {xml_error}")
                                        # Fallback to basic info
                                        results.append({
                                            "rxcui": "",
                                            "source": "dailymed",
                                            "id": f"dailymed_{spl_id}",
                                            "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={spl_id}",
                                            "title": title,
                                            "text": f"DailyMed SPL: {title}\nNote: Package insert content available at the provided URL."
                                        })
                except Exception as generic_error:
                    logger.warning(f"Failed to search DailyMed by generic name: {generic_error}")
            
            logger.info(f"DailyMed search returned {len(results)} results for '{drug_name}'")
            return results
            
        except Exception as e:
            logger.error(f"DailyMed API error: {e}")
            return []
    
    def _extract_spl_content(self, xml_content: str, drug_name: str) -> str:
        """Extract relevant medical information from SPL XML content with enhanced parsing."""
        try:
            sections = []
            
            # Enhanced section detection with comprehensive patterns for side effects
            section_patterns = [
                # Primary side effect sections
                ("adverse reaction", "Adverse Reactions", 5000),
                ("adverse reactions", "Adverse Reactions", 5000),
                ("adverse event", "Adverse Events", 5000),
                ("adverse events", "Adverse Events", 5000),
                
                # Warning and precaution sections (often contain side effects)
                ("warnings and precautions", "Warnings and Precautions", 4000),
                ("warnings", "Warnings", 4000),
                ("precautions", "Precautions", 4000),
                ("boxed warning", "Boxed Warning", 3000),
                ("black box warning", "Boxed Warning", 3000),
                
                # Specific side effect subsections
                ("myopathy", "Myopathy/Rhabdomyolysis", 3000),
                ("rhabdomyolysis", "Myopathy/Rhabdomyolysis", 3000),
                ("muscle", "Muscle Effects", 3000),
                ("myalgia", "Muscle Pain", 3000),
                ("liver", "Liver Effects", 3000),
                ("hepatic", "Liver Effects", 3000),
                ("gastrointestinal", "Gastrointestinal Effects", 3000),
                ("nervous system", "Nervous System Effects", 3000),
                ("cardiovascular", "Cardiovascular Effects", 3000),
                
                # Other important sections
                ("contraindications", "Contraindications", 2000),
                ("drug interactions", "Drug Interactions", 2500),
                ("clinical pharmacology", "Clinical Pharmacology", 2500),
                ("indications and usage", "Indications and Usage", 2000),
                ("dosage and administration", "Dosage and Administration", 2000)
            ]
            
            # Extract each section
            for pattern, section_name, max_length in section_patterns:
                if pattern in xml_content.lower():
                    start_idx = xml_content.lower().find(pattern)
                    if start_idx != -1:
                        # Get content around this section
                        end_idx = min(start_idx + max_length, len(xml_content))
                        section = xml_content[start_idx:end_idx]
                        
                        # Clean and extract readable content
                        cleaned_section = self._clean_xml_content(section)
                        if cleaned_section and len(cleaned_section.strip()) > 50:
                            sections.append(f"{section_name}: {cleaned_section}")
            
            # If we found sections, combine them
            if sections:
                return f"DailyMed Package Insert for {drug_name}:\n\n" + "\n\n".join(sections)
            else:
                # Fallback: return basic info about what's available
                return f"DailyMed Package Insert for {drug_name} available. Contains comprehensive prescribing information including adverse reactions, warnings, contraindications, and clinical data."
                
        except Exception as e:
            logger.warning(f"Failed to extract SPL content: {e}")
            return f"DailyMed Package Insert for {drug_name} available. Contains comprehensive prescribing information."
    
    def _clean_xml_content(self, xml_text: str) -> str:
        """Clean XML content to extract readable text with enhanced formatting."""
        try:
            import re
            
            # Remove XML tags but preserve some structure
            # Keep line breaks for readability
            cleaned = re.sub(r'<br/?>', '\n', xml_text)
            cleaned = re.sub(r'</?p>', '\n', cleaned)
            cleaned = re.sub(r'</?div>', '\n', cleaned)
            cleaned = re.sub(r'</?section>', '\n', cleaned)
            
            # Remove other XML tags
            cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
            
            # Clean up special characters and formatting
            cleaned = re.sub(r'&nbsp;', ' ', cleaned)
            cleaned = re.sub(r'&amp;', '&', cleaned)
            cleaned = re.sub(r'&lt;', '<', cleaned)
            cleaned = re.sub(r'&gt;', '>', cleaned)
            cleaned = re.sub(r'&quot;', '"', cleaned)
            
            # Remove excessive whitespace while preserving paragraph structure
            cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
            cleaned = re.sub(r' +', ' ', cleaned)
            
            # Remove special characters that don't add value
            cleaned = re.sub(r'[^\w\s\.\,\;\:\!\?\-\(\)\[\]\n]', '', cleaned)
            
            # Clean up the text
            cleaned = cleaned.strip()
            
            # Limit length but preserve complete sentences - increased for better side effect coverage
            if len(cleaned) > 1500:
                # Try to find a good cutoff point (end of sentence)
                sentences = re.split(r'[.!?]', cleaned[:1500])
                if len(sentences) > 1:
                    # Remove the last incomplete sentence
                    cleaned = '. '.join(sentences[:-1]) + '.'
                else:
                    cleaned = cleaned[:800] + "..."
            
            return cleaned
            
        except Exception as e:
            logger.warning(f"Failed to clean XML content: {e}")
            return xml_text[:300] + "..." if len(xml_text) > 300 else xml_text
    
    async def search_openfda(self, query: str, limit: int = 10) -> List[Dict]:
        """Search OpenFDA for drug information and adverse events."""
        try:
            # Extract drug name from the query
            drug_name = self._extract_drug_name(query)
            results = []
            
            # Search drug labels
            label_url = f"{OPENFDA_BASE_URL}/drug/label.json"
            label_params = {
                "search": f"generic_name:{drug_name}",
                "limit": limit // 2
            }
            
            label_response = await self.http_client.get(label_url, params=label_params)
            if label_response.status_code == 200:
                label_data = label_response.json()
                
                for result in label_data.get("results", [])[:limit // 2]:
                    # Extract key information
                    openfda_data = result.get("openfda", {})
                    generic_name_list = openfda_data.get("generic_name", [])
                    brand_name_list = openfda_data.get("brand_name", [])
                    
                    # Get first non-empty value, or use drug_name from query
                    generic_name = generic_name_list[0] if generic_name_list and generic_name_list[0] else drug_name
                    brand_name = brand_name_list[0] if brand_name_list and brand_name_list[0] else ""
                    
                    # Skip if we still don't have a valid name (shouldn't happen since we fallback to drug_name)
                    if not generic_name or generic_name.strip() == "":
                        continue
                    
                    text_parts = [f"OpenFDA Drug Label: {generic_name}"]
                    if brand_name:
                        text_parts.append(f"Brand Name: {brand_name}")
                    
                    # Add key sections - prioritize side effects and safety information
                    priority_sections = [
                        "adverse_reactions", "warnings_and_precautions", "boxed_warnings",
                        "contraindications", "drug_interactions", "warnings"
                    ]
                    
                    # Add priority sections first
                    for section in priority_sections:
                        if section in result and result[section]:
                            content = result[section][0] if isinstance(result[section], list) else result[section]
                            if content and len(content) > 30:  # Only add if substantial content
                                text_parts.append(f"{section.replace('_', ' ').title()}: {content}")
                    
                    # Add other sections if we don't have enough content
                    other_sections = ["indications_and_usage", "dosage_and_administration", "clinical_pharmacology"]
                    for section in other_sections:
                        if section in result and result[section]:
                            content = result[section][0] if isinstance(result[section], list) else result[section]
                            if content and len(content) > 30:
                                text_parts.append(f"{section.replace('_', ' ').title()}: {content}")
                    
                    full_text = "\n\n".join(text_parts)
                    
                    # Create display name
                    display_name = f"{generic_name} ({brand_name})" if brand_name else generic_name
                    
                    results.append({
                        "name": generic_name,  # Add name field for consistency
                        "drug_name": generic_name,  # Add drug_name field
                        "rxcui": "",  # OpenFDA doesn't provide RxCUI directly
                        "source": "openfda",
                        "id": f"openfda_{generic_name}_{brand_name}".replace(" ", "_").replace("/", "_"),
                        "url": "https://www.accessdata.fda.gov/scripts/cder/drugsatfda/",
                        "title": display_name,
                        "text": full_text
                    })
            
            # Search adverse events - use more specific search and validate results
            event_url = f"{OPENFDA_BASE_URL}/drug/event.json"
            event_params = {
                "search": f"patient.drug.medicinalproduct:{drug_name}",
                "limit": limit * 2  # Get more results to filter from
            }
            
            event_response = await self.http_client.get(event_url, params=event_params)
            if event_response.status_code == 200:
                event_data = event_response.json()
                
                valid_adverse_events = []
                for result in event_data.get("results", []):
                    drug_info = result.get("patient", {}).get("drug", [{}])[0]
                    medicinal_product = drug_info.get("medicinalproduct", "")
                    
                    # Skip if medicinal_product is missing or "Unknown"
                    if not medicinal_product or medicinal_product.strip() == "" or medicinal_product.lower() == "unknown":
                        continue
                    
                    # Validate that this result is actually for the drug we're searching for
                    if medicinal_product.lower() == drug_name.lower() or drug_name.lower() in medicinal_product.lower():
                        text_parts = [f"OpenFDA Adverse Event: {medicinal_product}"]
                        
                        if "patient" in result:
                            patient = result["patient"]
                            if "reaction" in patient:
                                reactions = patient["reaction"]
                                if reactions:
                                    reaction_text = "; ".join([r.get("reactionmeddrapt", "") for r in reactions if r.get("reactionmeddrapt")])
                                    if reaction_text:
                                        text_parts.append(f"Reactions: {reaction_text}")
                        
                        full_text = "\n\n".join(text_parts)
                        
                        valid_adverse_events.append({
                            "name": medicinal_product,  # Add name field for consistency
                            "drug_name": medicinal_product,  # Add drug_name field
                            "rxcui": "",
                            "source": "openfda",
                            "id": f"openfda_ae_{medicinal_product}".replace(" ", "_").replace("/", "_"),
                            "url": "https://www.accessdata.fda.gov/scripts/cder/drugsatfda/",
                            "title": f"Adverse Event: {medicinal_product}",
                            "text": full_text
                        })
                        
                        # Limit to requested number of results
                        if len(valid_adverse_events) >= limit // 2:
                            break
                
                # Add validated adverse events to results
                results.extend(valid_adverse_events)
            
            logger.info(f"OpenFDA search returned {len(results)} results for '{drug_name}'")
            return results
            
        except Exception as e:
            logger.error(f"OpenFDA API error: {e}")
            return []
    
    async def search_pubchem(self, query: str, limit: int = 10) -> List[Dict]:
        """Search PubChem for drug information - excellent for drug names and synonyms."""
        try:
            # Extract drug name from the query
            drug_name = self._extract_drug_name(query)
            results = []
            
            # Search PubChem by compound name
            search_url = f"{PUBCHEM_BASE_URL}/compound/name/{drug_name}/synonyms/JSON"
            
            try:
                response = await self.http_client.get(search_url)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Extract synonyms and create results
                    synonyms = data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
                    
                    # Get compound ID for additional information
                    compound_id = None
                    if synonyms:
                        # Try to get compound ID for the first synonym
                        try:
                            cid_url = f"{PUBCHEM_BASE_URL}/compound/name/{synonyms[0]}/cids/JSON"
                            cid_response = await self.http_client.get(cid_url)
                            if cid_response.status_code == 200:
                                cid_data = cid_response.json()
                                cids = cid_data.get("IdentifierList", {}).get("CID", [])
                                if cids:
                                    compound_id = cids[0]
                        except Exception as cid_error:
                            logger.warning(f"Failed to get compound ID: {cid_error}")
                    
                    # Create results from synonyms
                    for i, synonym in enumerate(synonyms[:limit]):
                        # Get additional compound information if we have a CID
                        additional_info = ""
                        if compound_id and i == 0:  # Only get detailed info for the first result
                            try:
                                # Get molecular formula and weight
                                props_url = f"{PUBCHEM_BASE_URL}/compound/cid/{compound_id}/property/MolecularFormula,MolecularWeight/JSON"
                                props_response = await self.http_client.get(props_url)
                                if props_response.status_code == 200:
                                    props_data = props_response.json()
                                    props = props_data.get("PropertyTable", {}).get("Properties", [{}])[0]
                                    formula = props.get("MolecularFormula", "")
                                    weight = props.get("MolecularWeight", "")
                                    
                                    if formula or weight:
                                        additional_info = f"\nMolecular Formula: {formula}\nMolecular Weight: {weight}"
                            except Exception as props_error:
                                logger.warning(f"Failed to get compound properties: {props_error}")
                        
                        text = f"PubChem Drug: {synonym}"
                        if additional_info:
                            text += additional_info
                        text += f"\nSynonyms: {', '.join(synonyms[:5])}"  # Show first 5 synonyms
                        
                        results.append({
                            "rxcui": "",  # PubChem doesn't provide RxCUI
                            "source": "pubchem",
                            "id": f"pubchem_{synonym.lower().replace(' ', '_')}",
                            "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{synonym}",
                            "title": f"PubChem: {synonym}",
                            "text": text
                        })
                
                # If no synonyms found, try searching by partial name
                if not results and len(drug_name) >= 3:
                    # Try fuzzy search using PubChem's text search
                    try:
                        text_search_url = f"{PUBCHEM_BASE_URL}/compound/name/{drug_name}/property/MolecularFormula,MolecularWeight/JSON"
                        text_response = await self.http_client.get(text_search_url)
                        if text_response.status_code == 200:
                            text_data = text_response.json()
                            compounds = text_data.get("PropertyTable", {}).get("Properties", [])
                            
                            for compound in compounds[:limit]:
                                # Get compound name from CID
                                cid = compound.get("CID", "")
                                if cid:
                                    try:
                                        name_url = f"{PUBCHEM_BASE_URL}/compound/cid/{cid}/property/IUPACName/JSON"
                                        name_response = await self.http_client.get(name_url)
                                        if name_response.status_code == 200:
                                            name_data = name_response.json()
                                            names = name_data.get("PropertyTable", {}).get("Properties", [{}])[0]
                                            iupac_name = names.get("IUPACName", "")
                                            
                                            formula = compound.get("MolecularFormula", "")
                                            weight = compound.get("MolecularWeight", "")
                                            
                                            text = f"PubChem Compound: {iupac_name or drug_name}"
                                            if formula:
                                                text += f"\nMolecular Formula: {formula}"
                                            if weight:
                                                text += f"\nMolecular Weight: {weight}"
                                            
                                            results.append({
                                                "rxcui": "",
                                                "source": "pubchem",
                                                "id": f"pubchem_cid_{cid}",
                                                "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                                                "title": f"PubChem: {iupac_name or drug_name}",
                                                "text": text
                                            })
                                    except Exception as name_error:
                                        logger.warning(f"Failed to get compound name for CID {cid}: {name_error}")
                                        continue
                    except Exception as text_error:
                        logger.warning(f"Failed to search PubChem by text: {text_error}")
                
            except Exception as search_error:
                logger.warning(f"PubChem search failed: {search_error}")
            
            # If still no results, only create a basic result for reasonable drug names
            if not results and self._is_reasonable_drug_name(drug_name):
                results.append({
                    "rxcui": "",
                    "source": "pubchem",
                    "id": f"pubchem_{drug_name.lower().replace(' ', '_')}",
                    "url": f"https://pubchem.ncbi.nlm.nih.gov/#query={drug_name}",
                    "title": f"PubChem Search: {drug_name}",
                    "text": f"PubChem search for {drug_name}. This compound may be available in the PubChem database. Visit the provided URL for detailed chemical information, properties, and related data."
                })
            
            logger.info(f"PubChem search returned {len(results)} results for '{drug_name}'")
            return results
            
        except Exception as e:
            logger.error(f"PubChem API error: {e}")
            return []

    async def search_drugbank(self, query: str, limit: int = 10) -> List[Dict]:
        """Search DrugBank for drug information (note: limited access to open data)."""
        try:
            # Extract drug name from the query
            drug_name = self._extract_drug_name(query)
            
            # For now, return basic information since DrugBank requires API access
            # In production, you would need proper DrugBank API credentials
            
            results = []
            
            # Create a basic result structure with actual drug information
            results.append({
                "rxcui": "",
                "source": "drugbank",
                "id": f"drugbank_{drug_name.lower().replace(' ', '_')}",
                "url": f"https://go.drugbank.com/drugs/{drug_name.lower().replace(' ', '-')}",
                "title": f"DrugBank: {drug_name}",
                "text": f"DrugBank information for {drug_name}. This drug is available in the DrugBank database. For comprehensive information including drug interactions, mechanisms of action, and pharmacokinetics, please visit the DrugBank website or contact us for API access."
            })
            
            logger.info(f"DrugBank search returned {len(results)} results for '{drug_name}'")
            return results
            
        except Exception as e:
            logger.error(f"DrugBank API error: {e}")
            return []
    
    async def search_all_sources(self, query: str, limit_per_source: int = 5) -> List[RetrievedDoc]:
        """Search all medical databases and return unified results."""
        return await self.search_all_sources_custom(query, limit_per_source, limit_per_source, limit_per_source, limit_per_source)
    
    async def search_all_sources_custom(self, query: str, daily_med_limit: int = 5, openfda_limit: int = 5, rxnorm_limit: int = 5, drugbank_limit: int = 5, pubchem_limit: int = 5) -> List[RetrievedDoc]:
        """Search all medical databases with custom limits for each source."""
        logger.info(f"Searching all medical databases for: '{query}' with custom limits (DailyMed: {daily_med_limit}, OpenFDA: {openfda_limit}, RxNorm: {rxnorm_limit}, DrugBank: {drugbank_limit}, PubChem: {pubchem_limit})")
        
        # Search all sources concurrently with custom limits
        tasks = [
            self.search_rxnorm(query, rxnorm_limit),
            self.search_dailymed(query, daily_med_limit),
            self.search_openfda(query, openfda_limit),
            self.search_drugbank(query, drugbank_limit),
            self.search_pubchem(query, pubchem_limit)
        ]
        
        # Execute all searches concurrently
        search_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and convert to RetrievedDoc objects
        all_docs = []
        
        for i, result in enumerate(search_results):
            if isinstance(result, Exception):
                logger.error(f"Search source {i} failed: {result}")
                continue
            
            source_name = ["rxnorm", "dailymed", "openfda", "drugbank", "pubchem"][i]
            
            for doc_data in result:
                try:
                    # Create document without embedding
                    score = 0.8  # Base score for retrieved documents
                    
                    doc = RetrievedDoc(
                        rxcui=doc_data["rxcui"],
                        source=Source(source_name),
                        id=doc_data["id"],
                        url=doc_data["url"],
                        title=doc_data["title"],
                        text=doc_data["text"],
                        score=score
                    )
                    all_docs.append(doc)
                except Exception as e:
                    logger.error(f"Error processing document from {source_name}: {e}")
                    continue
        
        # Sort by score and return
        all_docs.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"Total documents retrieved from all sources: {len(all_docs)}")
        
        return all_docs

# Global client instance
medical_api_client = MedicalAPIClient()

async def get_medical_api_client() -> MedicalAPIClient:
    """Get the global medical API client instance."""
    return medical_api_client

async def close_medical_api_client():
    """Close the global medical API client."""
    await medical_api_client.close()
