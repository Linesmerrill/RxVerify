"""
Missing Drug Request Manager

Manages missing drug requests, API searches, and approval workflow.
"""

import logging
import re
import uuid
from typing import List, Dict, Optional, Any, Iterable
from datetime import datetime
from app.mongodb_config import mongodb_config
from app.drug_database_schema import MissingDrugRequest, MissingDrugStatus
from app.medical_apis import MedicalAPIClient
from app.drug_database_manager import drug_db_manager
from app.drug_database_schema import DrugEntry, DrugType, DrugStatus

logger = logging.getLogger(__name__)


class MissingDrugManager:
    """Manager for missing drug requests."""
    
    _UPPERCASE_WORDS = {
        "MG", "ML", "MCG", "G", "KG", "MG/ML", "MCG/ML", "IU", "MEQ",
        "MMOL", "L", "ML/HR", "MG/HR", "HR", "IN", "IV"
    }
    _LOWERCASE_WORDS = {"of", "the", "and", "or", "in", "on", "at", "to", "for", "with", "by"}
    _DOSAGE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|unit|units|meq|mmol|%)\b", re.IGNORECASE)
    _FORM_WORDS_PATTERN = re.compile(
        r"\b(tablet|tablets|tab|tabs|capsule|capsules|cap|caps|oral|solution|suspension|injection|injectable|cream|ointment|patch|spray|drops|drop|syrup|elixir|powder|pack|packet|extended-release|extended release|delayed-release|delayed release|chewable|topical|gel|lozenge|suppository|kit)\b",
        re.IGNORECASE,
    )
    
    def __init__(self):
        self.collection = None
        self.api_client = None
    
    @staticmethod
    def _normalize_whitespace(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()
    
    @classmethod
    def _format_name(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = cls._normalize_whitespace(value)
        if not value:
            return None
        
        formatted = value.title()
        
        for unit in cls._UPPERCASE_WORDS:
            formatted = re.sub(rf"\b{re.escape(unit.title())}\b", unit, formatted)
        
        for word in cls._LOWERCASE_WORDS:
            formatted = re.sub(rf"\b{re.escape(word.title())}\b", word, formatted)
        
        return formatted
    
    @classmethod
    def _strip_strength_and_forms(cls, value: Optional[str]) -> str:
        if not value:
            return ""
        
        cleaned = cls._normalize_whitespace(value)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)  # Remove bracketed brand hints
        cleaned = re.sub(r"\(.*?\)", "", cleaned)  # Remove parenthetical notes
        cleaned = cls._DOSAGE_PATTERN.sub("", cleaned)
        cleaned = cls._FORM_WORDS_PATTERN.sub("", cleaned)
        cleaned = re.sub(r"[\/\-]+", " ", cleaned)
        cleaned = cls._normalize_whitespace(cleaned)
        return cleaned
    
    @classmethod
    def _normalize_term(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = cls._normalize_whitespace(value).lower()
        return normalized or None
    
    @classmethod
    def _extract_brand_names(
        cls,
        data: Optional[Dict[str, Any]],
        api_name: Optional[str],
        request_name: Optional[str]
    ) -> List[str]:
        candidates: List[str] = []
        
        def add_candidate(raw: Optional[str]):
            if not raw:
                return
            parts = re.split(r"[;,|]", raw)
            for part in parts:
                cleaned = cls._strip_strength_and_forms(part)
                if cleaned:
                    candidates.append(cleaned)
        
        if data:
            if isinstance(data.get("brand_names"), list):
                for item in data["brand_names"]:
                    add_candidate(item)
            else:
                add_candidate(data.get("brand_names"))
            
            add_candidate(data.get("brand_name"))
            add_candidate(data.get("brands"))
            add_candidate(data.get("synonym"))
            add_candidate(data.get("title"))
        
        for value in (api_name, request_name):
            if value and "[" in value:
                bracketed = re.findall(r"\[(.*?)\]", value)
                for entry in bracketed:
                    add_candidate(entry)
        
        formatted = {
            cls._format_name(candidate)
            for candidate in candidates
            if candidate
        }
        
        return sorted(name for name in formatted if name)
    
    @classmethod
    def _build_search_terms(cls, values: Iterable[Optional[str]]) -> List[str]:
        terms: set[str] = set()
        
        for value in values:
            if not value:
                continue
            normalized = cls._normalize_term(value)
            if not normalized:
                continue
            
            variations = {
                normalized,
                normalized.replace("-", " "),
                normalized.replace(" ", ""),
            }
            
            for variation in variations:
                clean_variation = cls._normalize_term(variation)
                if clean_variation:
                    terms.add(clean_variation)
        
        return sorted(term for term in terms if term)
    
    async def initialize(self):
        """Initialize the missing drug manager."""
        try:
            db = await mongodb_config.connect()
            self.collection = db["missing_drugs"]
            
            # Create indexes
            await self.collection.create_index("request_id", unique=True)
            await self.collection.create_index("status")
            await self.collection.create_index("created_at")
            await self.collection.create_index("drug_name")
            
            # Initialize API client
            self.api_client = MedicalAPIClient()
            
            logger.info("Missing drug manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize missing drug manager: {str(e)}")
            raise
    
    async def create_request(
        self, 
        drug_name: str, 
        search_query: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> MissingDrugRequest:
        """Create a new missing drug request."""
        try:
            request_id = str(uuid.uuid4())
            
            request = MissingDrugRequest(
                request_id=request_id,
                drug_name=drug_name,
                search_query=search_query,
                status=MissingDrugStatus.PENDING,
                created_by_ip=ip_address,
                created_by_user_agent=user_agent
            )
            
            await self.collection.insert_one(request.dict())
            logger.info(f"Created missing drug request: {drug_name} ({request_id})")
            
            return request
        except Exception as e:
            logger.error(f"Failed to create missing drug request: {str(e)}")
            raise
    
    async def search_apis(self, request_id: str) -> Dict[str, Any]:
        """Search external APIs for the missing drug."""
        try:
            request_doc = await self.collection.find_one({"request_id": request_id})
            if not request_doc:
                raise ValueError(f"Request {request_id} not found")
            
            request = MissingDrugRequest(**request_doc)
            drug_name = request.drug_name
            
            logger.info(f"Searching APIs for missing drug: {drug_name}")
            
            # Search all APIs
            api_results = []
            
            # Search RxNorm
            try:
                rxnorm_results = await self.api_client.search_rxnorm(drug_name, limit=5)
                if rxnorm_results:
                    api_results.extend([{"source": "RxNorm", **r} for r in rxnorm_results])
            except Exception as e:
                logger.warning(f"RxNorm search failed: {str(e)}")
            
            # Search DailyMed
            try:
                dailymed_results = await self.api_client.search_dailymed(drug_name, limit=5)
                if dailymed_results:
                    api_results.extend([{"source": "DailyMed", **r} for r in dailymed_results])
            except Exception as e:
                logger.warning(f"DailyMed search failed: {str(e)}")
            
            # Search OpenFDA
            try:
                openfda_results = await self.api_client.search_openfda(drug_name, limit=5)
                if openfda_results:
                    api_results.extend([{"source": "OpenFDA", **r} for r in openfda_results])
            except Exception as e:
                logger.warning(f"OpenFDA search failed: {str(e)}")
            
            # Update request with results
            status = MissingDrugStatus.FOUND if api_results else MissingDrugStatus.NOT_FOUND
            found_data = api_results[0] if api_results else None
            
            update_data = {
                "api_search_results": api_results,
                "api_search_performed": True,
                "api_search_timestamp": datetime.utcnow(),
                "status": status,
                "found_drug_data": found_data,
                "updated_at": datetime.utcnow()
            }
            
            await self.collection.update_one(
                {"request_id": request_id},
                {"$set": update_data}
            )
            
            logger.info(f"API search completed for {drug_name}: {len(api_results)} results")
            
            return {
                "request_id": request_id,
                "drug_name": drug_name,
                "results": api_results,
                "found": len(api_results) > 0,
                "status": status
            }
            
        except Exception as e:
            logger.error(f"Failed to search APIs for request {request_id}: {str(e)}")
            raise
    
    async def get_request(self, request_id: str) -> Optional[MissingDrugRequest]:
        """Get a missing drug request by ID."""
        try:
            doc = await self.collection.find_one({"request_id": request_id})
            if doc:
                return MissingDrugRequest(**doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get request {request_id}: {str(e)}")
            return None
    
    async def submit_suggestion(
        self,
        request_id: str,
        selected_drug_data: Dict[str, Any]
    ) -> bool:
        """Submit a suggestion with selected drug data."""
        try:
            # Update request with selected drug data
            update_data = {
                "selected_drug_data": selected_drug_data,
                "found_drug_data": selected_drug_data,  # Also set as found_drug_data
                "status": MissingDrugStatus.FOUND,
                "updated_at": datetime.utcnow()
            }
            
            result = await self.collection.update_one(
                {"request_id": request_id},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                # Increment suggestion count for this drug name (normalized)
                drug_name = selected_drug_data.get("name") or selected_drug_data.get("drug_name", "").lower().strip()
                await self._increment_suggestion_count(drug_name)
                logger.info(f"Suggestion submitted for request {request_id}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to submit suggestion: {str(e)}")
            return False
    
    async def _increment_suggestion_count(self, drug_name: str):
        """Increment suggestion count for a drug name."""
        try:
            # Use a separate collection to track suggestion counts
            db = await mongodb_config.connect()
            counts_collection = db["drug_suggestion_counts"]
            
            # Normalize drug name
            normalized_name = drug_name.lower().strip()
            
            await counts_collection.update_one(
                {"drug_name": normalized_name},
                {"$inc": {"count": 1}, "$set": {"last_suggested": datetime.utcnow()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to increment suggestion count: {str(e)}")
    
    async def get_suggestion_count(self, drug_name: str) -> int:
        """Get suggestion count for a drug name."""
        try:
            db = await mongodb_config.connect()
            counts_collection = db["drug_suggestion_counts"]
            
            normalized_name = drug_name.lower().strip()
            doc = await counts_collection.find_one({"drug_name": normalized_name})
            
            return doc.get("count", 0) if doc else 0
        except Exception as e:
            logger.error(f"Failed to get suggestion count: {str(e)}")
            return 0
    
    async def list_requests(
        self, 
        status: Optional[MissingDrugStatus] = None,
        limit: int = 50,
        sort_by_priority: bool = True
    ) -> List[MissingDrugRequest]:
        """List missing drug requests, optionally sorted by priority (suggestion count)."""
        try:
            query = {}
            if status:
                query["status"] = status
            
            # Get all matching requests
            cursor = self.collection.find(query)
            requests = []
            
            async for doc in cursor:
                requests.append(MissingDrugRequest(**doc))
            
            # Sort by priority if requested
            if sort_by_priority:
                # Get suggestion counts for each drug
                db = await mongodb_config.connect()
                counts_collection = db["drug_suggestion_counts"]
                
                # Create a map of drug names to counts
                counts_map = {}
                async for count_doc in counts_collection.find({}):
                    counts_map[count_doc["drug_name"]] = count_doc.get("count", 0)
                
                # Sort by suggestion count (descending), then by created_at (descending)
                def get_priority(request: MissingDrugRequest) -> tuple:
                    drug_name = request.drug_name.lower().strip()
                    count = counts_map.get(drug_name, 0)
                    return (-count, -request.created_at.timestamp())
                
                requests.sort(key=get_priority)
            
            # Limit results if requested (limit <= 0 means return all)
            if limit and limit > 0:
                return requests[:limit]
            return requests
        except Exception as e:
            logger.error(f"Failed to list requests: {str(e)}")
            return []
    
    async def get_total_requests(self) -> int:
        """Get total count of missing drug requests."""
        try:
            return await self.collection.count_documents({})
        except Exception as e:
            logger.error(f"Failed to count missing drug requests: {str(e)}")
            return 0
    
    async def approve_and_add(
        self, 
        request_id: str, 
        approved_by: str = "admin"
    ) -> Dict[str, Any]:
        """Approve a missing drug request and add it to the database."""
        try:
            request = await self.get_request(request_id)
            if not request:
                raise ValueError(f"Request {request_id} not found")
            
            if request.status == MissingDrugStatus.APPROVED:
                return {"success": False, "message": "Request already approved"}
            
            # Use selected_drug_data if available, otherwise use found_drug_data
            drug_data = request.selected_drug_data or request.found_drug_data
            
            # Create drug entry from request data
            drug_entry = await self._create_drug_entry(request, drug_data)
            
            # Insert drug into database
            success = await drug_db_manager.insert_drug(drug_entry)
            
            if not success:
                raise Exception("Failed to insert drug into database")
            
            # Update request status
            update_data = {
                "status": MissingDrugStatus.APPROVED,
                "approved_at": datetime.utcnow(),
                "approved_by": approved_by,
                "added_drug_id": drug_entry.drug_id,
                "updated_at": datetime.utcnow()
            }
            
            await self.collection.update_one(
                {"request_id": request_id},
                {"$set": update_data}
            )
            
            logger.info(f"Approved and added drug: {drug_entry.name} ({drug_entry.drug_id})")
            
            return {
                "success": True,
                "drug_id": drug_entry.drug_id,
                "drug_name": drug_entry.name,
                "message": "Drug added successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to approve request {request_id}: {str(e)}")
            raise
    
    async def _create_drug_entry(self, request: MissingDrugRequest, drug_data: Optional[Dict[str, Any]] = None) -> DrugEntry:
        """Create a DrugEntry from a MissingDrugRequest."""
        drug_id = f"missing_{request.request_id[:8]}"
        
        # Use provided drug_data or fall back to request data
        data = drug_data or request.selected_drug_data or request.found_drug_data or {}
        
        request_name = request.drug_name or data.get("drug_name") or data.get("name") or ""
        request_name_formatted = self._format_name(request_name) or request_name.strip() or "Unknown Drug"
        
        api_name = data.get("name") or data.get("title")
        cleaned_generic_candidate = self._strip_strength_and_forms(api_name or request_name)
        formatted_generic_candidate = self._format_name(cleaned_generic_candidate) or request_name_formatted
        
        brand_names = self._extract_brand_names(data, api_name, request_name)
        brand_names = [
            bn for bn in brand_names
            if self._normalize_term(bn) != self._normalize_term(formatted_generic_candidate)
        ]
        brand_normalized = {self._normalize_term(name) for name in brand_names}
        
        primary_search_term = (
            self._normalize_term(request.drug_name)
            or self._normalize_term(request.search_query)
            or self._normalize_term(formatted_generic_candidate)
            or self._normalize_term(api_name)
        )
        
        search_terms = self._build_search_terms([
            request.drug_name,
            request.search_query,
            api_name,
            data.get("synonym"),
            formatted_generic_candidate,
            request_name_formatted,
            *(brand_names or []),
        ])
        
        if not primary_search_term and search_terms:
            primary_search_term = search_terms[0]
        elif not primary_search_term:
            primary_search_term = self._normalize_term(request_name_formatted)
        
        if primary_search_term and primary_search_term not in search_terms:
            search_terms.append(primary_search_term)
        
        drug_type = DrugType.GENERIC
        name = formatted_generic_candidate or request_name_formatted
        generic_name = None
        
        api_term_type = (data.get("term_type") or "").upper()
        normalized_primary = self._normalize_term(name) or primary_search_term
        
        is_combination = False
        if normalized_primary:
            is_combination = any(separator in normalized_primary for separator in [" and ", " + ", " / "])
        
        if is_combination:
            drug_type = DrugType.COMBINATION
        elif api_term_type in {"SBD", "SBDG", "SBDF", "BPCK", "BN"} or (
            normalized_primary and brand_normalized and normalized_primary in brand_normalized
        ):
            drug_type = DrugType.BRAND
            name = self._format_name(api_name) or request_name_formatted
            generic_name_candidate = formatted_generic_candidate
            if generic_name_candidate and self._normalize_term(generic_name_candidate) != self._normalize_term(name):
                generic_name = generic_name_candidate
        else:
            drug_type = DrugType.GENERIC
            name = formatted_generic_candidate or request_name_formatted
            generic_name = None
        
        rxnorm_id = str(data.get("rxcui")) if data.get("rxcui") else None
        drug_class = data.get("drug_class")
        manufacturer = data.get("manufacturer")
        
        common_uses_raw = data.get("common_uses")
        if isinstance(common_uses_raw, list):
            common_uses = common_uses_raw
        elif common_uses_raw:
            common_uses = [str(common_uses_raw)]
        else:
            common_uses = []
        
        source_label = data.get("source")
        if source_label:
            data_source = f"Missing Drug Request ({self._format_name(str(source_label))})"
        else:
            data_source = "Missing Drug Request"
        
        if not search_terms:
            search_terms = [primary_search_term] if primary_search_term else []
        else:
            search_terms = sorted(set(search_terms))
        
        drug_entry = DrugEntry(
            drug_id=drug_id,
            name=name or request_name_formatted,
            drug_type=drug_type,
            generic_name=generic_name,
            brand_names=brand_names,
            manufacturer=manufacturer,
            drug_class=drug_class,
            common_uses=common_uses,
            rxnorm_id=rxnorm_id,
            primary_search_term=primary_search_term,
            search_terms=search_terms,
            status=DrugStatus.ACTIVE,
            data_source=data_source
        )
        
        return drug_entry
    
    async def reject_request(self, request_id: str, approved_by: str = "admin") -> bool:
        """Reject a missing drug request."""
        try:
            update_data = {
                "status": MissingDrugStatus.REJECTED,
                "approved_at": datetime.utcnow(),
                "approved_by": approved_by,
                "updated_at": datetime.utcnow()
            }
            
            result = await self.collection.update_one(
                {"request_id": request_id},
                {"$set": update_data}
            )
            
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to reject request {request_id}: {str(e)}")
            return False


# Global instance
missing_drug_manager = MissingDrugManager()

