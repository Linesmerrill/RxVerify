"""
MongoDB Schema for Curated Drug Database

This module defines the schema for our local drug database that will contain
clean, curated drug information for fast searching without external API calls.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class DrugType(str, Enum):
    """Types of drug entries."""
    GENERIC = "generic"           # Generic drug name (e.g., "Metformin")
    BRAND = "brand"               # Brand name (e.g., "Glucophage")
    COMBINATION = "combination"    # Multi-drug combination (e.g., "Metformin-Glyburide")


class DrugStatus(str, Enum):
    """Status of drug in database."""
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    RECALLED = "recalled"
    HIDDEN = "hidden"              # Hidden due to poor ratings


class VoteType(str, Enum):
    """Types of votes."""
    UPVOTE = "upvote"
    DOWNVOTE = "downvote"


class DrugVote(BaseModel):
    """Individual vote on a drug."""
    
    vote_id: str = Field(..., description="Unique identifier for this vote")
    drug_id: str = Field(..., description="ID of the drug being voted on")
    user_id: Optional[str] = Field(None, description="ID of user who voted (optional for anonymous)")
    vote_type: VoteType = Field(..., description="Type of vote")
    reason: Optional[str] = Field(None, description="Optional reason for the vote")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the vote was cast")
    ip_address: Optional[str] = Field(None, description="IP address for anonymous voting")
    user_agent: Optional[str] = Field(None, description="User agent for anonymous voting")


class DrugRating(BaseModel):
    """Aggregated rating information for a drug."""
    
    drug_id: str = Field(..., description="ID of the drug")
    total_votes: int = Field(default=0, description="Total number of votes")
    upvotes: int = Field(default=0, description="Number of upvotes")
    downvotes: int = Field(default=0, description="Number of downvotes")
    rating_score: float = Field(default=0.0, description="Calculated rating score (-1.0 to 1.0)")
    is_hidden: bool = Field(default=False, description="Whether drug is hidden due to poor ratings")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last rating update")
    
    def calculate_rating_score(self) -> float:
        """Calculate rating score based on votes."""
        if self.total_votes == 0:
            return 0.0
        
        # Simple ratio: (upvotes - downvotes) / total_votes
        # Range: -1.0 (all downvotes) to 1.0 (all upvotes)
        return (self.upvotes - self.downvotes) / self.total_votes
    
    def should_be_hidden(self, threshold: float = -0.5) -> bool:
        """Determine if drug should be hidden based on rating threshold."""
        return self.rating_score <= threshold and self.total_votes >= 3  # Need at least 3 votes


class DrugEntry(BaseModel):
    """Main drug entry in our curated database."""
    
    # Core identification
    drug_id: str = Field(..., description="Unique identifier for this drug entry")
    name: str = Field(..., description="Primary drug name")
    drug_type: DrugType = Field(..., description="Type of drug entry")
    
    # Generic drug information (for brand/combination drugs)
    generic_name: Optional[str] = Field(None, description="Generic name if this is a brand")
    generic_drug_id: Optional[str] = Field(None, description="Reference to generic drug")
    
    # Brand information
    brand_names: List[str] = Field(default_factory=list, description="All brand names for this drug")
    manufacturer: Optional[str] = Field(None, description="Primary manufacturer")
    
    # Combination drug information
    active_ingredients: List[str] = Field(default_factory=list, description="Active ingredients")
    combination_drug_ids: List[str] = Field(default_factory=list, description="References to component drugs")
    
    # Medical information
    drug_class: Optional[str] = Field(None, description="Drug class/therapeutic category")
    common_uses: List[str] = Field(default_factory=list, description="Common medical uses")
    rxnorm_id: Optional[str] = Field(None, description="RxNorm identifier")
    ndc_codes: List[str] = Field(default_factory=list, description="National Drug Codes")
    
    # Search optimization
    search_terms: List[str] = Field(default_factory=list, description="All searchable terms")
    primary_search_term: str = Field(..., description="Primary search term")
    
    # Status and metadata
    status: DrugStatus = Field(default=DrugStatus.ACTIVE, description="Current status")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    data_source: str = Field(..., description="Source of this data (FDA, RxNorm, etc.)")
    
    # Usage statistics
    search_count: int = Field(default=0, description="Number of times searched")
    last_searched: Optional[datetime] = Field(None, description="Last time this drug was searched")
    
    # Rating information
    rating_score: float = Field(default=0.0, description="Current rating score (-1.0 to 1.0)")
    total_votes: int = Field(default=0, description="Total number of votes received")
    upvotes: int = Field(default=0, description="Number of upvotes")
    downvotes: int = Field(default=0, description="Number of downvotes")


class DrugSearchResult(BaseModel):
    """Result format for drug searches."""
    
    drug_id: str
    name: str
    drug_type: DrugType
    generic_name: Optional[str] = None
    brand_names: List[str] = []
    drug_class: Optional[str] = None
    common_uses: List[str] = []
    manufacturer: Optional[str] = None
    rxnorm_id: Optional[str] = None
    
    # Search relevance
    relevance_score: float = Field(default=0.0, description="Search relevance score")
    match_type: str = Field(..., description="Type of match (exact, partial, brand, etc.)")
    
    # Rating information
    rating_score: float = Field(default=0.0, description="Current rating score (-1.0 to 1.0)")
    total_votes: int = Field(default=0, description="Total number of votes received")
    upvotes: int = Field(default=0, description="Number of upvotes")
    downvotes: int = Field(default=0, description="Number of downvotes")
    is_hidden: bool = Field(default=False, description="Whether drug is hidden due to poor ratings")


class DrugDatabaseStats(BaseModel):
    """Statistics about the drug database."""
    
    total_drugs: int
    generic_drugs: int
    brand_drugs: int
    combination_drugs: int
    active_drugs: int
    discontinued_drugs: int
    last_updated: datetime
    data_sources: List[str]


class MissingDrugStatus(str, Enum):
    """Status of missing drug request."""
    PENDING = "pending"           # Awaiting review
    FOUND = "found"               # Found in APIs, awaiting approval
    NOT_FOUND = "not_found"       # Not found in APIs, awaiting manual addition
    APPROVED = "approved"         # Approved and added to database
    REJECTED = "rejected"         # Rejected by admin


class MissingDrugRequest(BaseModel):
    """Request for a missing drug to be added to the database."""
    
    request_id: str = Field(..., description="Unique identifier for this request")
    drug_name: str = Field(..., description="Name of the drug that was searched")
    search_query: str = Field(..., description="Original search query")
    status: MissingDrugStatus = Field(default=MissingDrugStatus.PENDING, description="Current status")
    
    # API search results
    api_search_results: Optional[List[Dict[str, Any]]] = Field(None, description="Results from API searches")
    api_search_performed: bool = Field(default=False, description="Whether API search was performed")
    api_search_timestamp: Optional[datetime] = Field(None, description="When API search was performed")
    
    # Drug data if found
    found_drug_data: Optional[Dict[str, Any]] = Field(None, description="Drug data if found in APIs")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When request was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    created_by_ip: Optional[str] = Field(None, description="IP address of requester")
    created_by_user_agent: Optional[str] = Field(None, description="User agent of requester")
    
    # Approval information
    approved_at: Optional[datetime] = Field(None, description="When approved")
    approved_by: Optional[str] = Field(None, description="Who approved (admin identifier)")
    added_drug_id: Optional[str] = Field(None, description="Drug ID if added to database")
    
    # Selected drug data (user-selected from API results)
    selected_drug_data: Optional[Dict[str, Any]] = Field(None, description="User-selected drug data from API results")


# Example drug entries for reference
EXAMPLE_DRUGS = [
    # Generic Metformin
    DrugEntry(
        drug_id="metformin_generic",
        name="Metformin",
        drug_type=DrugType.GENERIC,
        drug_class="Biguanide",
        common_uses=["Type 2 diabetes", "Blood sugar control"],
        rxnorm_id="860975",
        primary_search_term="metformin",
        search_terms=["metformin", "glucophage", "fortamet", "glumetza"],
        data_source="RxNorm"
    ),
    
    # Brand Glucophage
    DrugEntry(
        drug_id="glucophage_brand",
        name="Glucophage",
        drug_type=DrugType.BRAND,
        generic_name="Metformin",
        generic_drug_id="metformin_generic",
        brand_names=["Glucophage", "Glucophage XR"],
        manufacturer="Bristol-Myers Squibb",
        drug_class="Biguanide",
        common_uses=["Type 2 diabetes", "Blood sugar control"],
        primary_search_term="glucophage",
        search_terms=["glucophage", "metformin"],
        data_source="FDA"
    ),
    
    # Combination drug
    DrugEntry(
        drug_id="metformin_glyburide_combo",
        name="Metformin-Glyburide",
        drug_type=DrugType.COMBINATION,
        active_ingredients=["Metformin", "Glyburide"],
        combination_drug_ids=["metformin_generic", "glyburide_generic"],
        drug_class="Antidiabetic Combination",
        common_uses=["Type 2 diabetes", "Blood sugar control"],
        primary_search_term="metformin glyburide",
        search_terms=["metformin glyburide", "metformin and glyburide", "glucovance"],
        data_source="FDA"
    )
]
