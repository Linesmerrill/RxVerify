"""
Missing Drug Request Manager

Manages missing drug requests, API searches, and approval workflow.
"""

import logging
import uuid
from typing import List, Dict, Optional, Any
from datetime import datetime
from app.mongodb_config import mongodb_config
from app.drug_database_schema import MissingDrugRequest, MissingDrugStatus
from app.medical_apis import MedicalAPIClient
from app.drug_database_manager import drug_db_manager
from app.drug_database_schema import DrugEntry, DrugType, DrugStatus

logger = logging.getLogger(__name__)


class MissingDrugManager:
    """Manager for missing drug requests."""
    
    def __init__(self):
        self.collection = None
        self.api_client = None
    
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
            
            # Limit results
            return requests[:limit]
        except Exception as e:
            logger.error(f"Failed to list requests: {str(e)}")
            return []
    
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
        drug_name = request.drug_name
        
        # Use provided drug_data or fall back to request data
        data = drug_data or request.selected_drug_data or request.found_drug_data
        
        # Try to extract data from API results if available
        drug_type = DrugType.GENERIC
        generic_name = None
        brand_names = []
        drug_class = None
        common_uses = []
        rxnorm_id = None
        manufacturer = None
        data_source = "User Request"
        
        if data:
            # Use drug name from data if available
            if "name" in data and data["name"]:
                drug_name = data["name"]
            elif "drug_name" in data and data["drug_name"]:
                drug_name = data["drug_name"]
            
            if "rxcui" in data:
                rxnorm_id = str(data["rxcui"])
            if "drug_class" in data:
                drug_class = data["drug_class"]
            if "common_uses" in data:
                common_uses = data["common_uses"] if isinstance(data["common_uses"], list) else [data["common_uses"]]
            if "manufacturer" in data:
                manufacturer = data["manufacturer"]
            if "source" in data:
                data_source = data["source"]
        
        # Create search terms
        search_terms = [drug_name.lower()]
        primary_search_term = drug_name.lower()
        
        drug_entry = DrugEntry(
            drug_id=drug_id,
            name=drug_name,
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

