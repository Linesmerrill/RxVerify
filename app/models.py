from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel

class Source(str, Enum):
    RXNORM = "rxnorm"
    DAILYMED = "dailymed"
    OPENFDA = "openfda"
    DRUGBANK = "drugbank"

class SourceRef(BaseModel):
    source: Source
    id: str
    url: Optional[str] = None

class FieldEvidence(BaseModel):
    value: str | Dict | List
    sources: List[SourceRef]

class UnifiedDrugRecord(BaseModel):
    rxcui: str
    name: str
    synonyms: List[str] = []
    indications: List[FieldEvidence] = []
    dosage: List[FieldEvidence] = []
    warnings: List[FieldEvidence] = []
    adverse_events: List[FieldEvidence] = []
    interactions: List[FieldEvidence] = []
    mechanism: List[FieldEvidence] = []
    references: List[SourceRef] = []

class RetrievedDoc(BaseModel):
    rxcui: Optional[str]
    source: Source
    id: str
    url: Optional[str]
    title: Optional[str]
    text: str
    score: float

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class DrugSearchResult(BaseModel):
    rxcui: str
    name: str
    generic_name: Optional[str] = None
    brand_names: List[str] = []
    common_uses: List[str] = []
    drug_class: Optional[str] = None
    source: str

class SearchResponse(BaseModel):
    results: List[DrugSearchResult]
    total_found: int
    processing_time_ms: float
