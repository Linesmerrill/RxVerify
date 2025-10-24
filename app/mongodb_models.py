"""
MongoDB Document Models
Pydantic models for MongoDB document validation and serialization
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId

class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic."""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")
        return field_schema

class FeedbackDocument(BaseModel):
    """Feedback document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    drug_name: str = Field(..., max_length=255)
    query: str = Field(..., max_length=500)
    is_positive: bool = Field(default=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class SearchMetricDocument(BaseModel):
    """Search metric document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    query: str = Field(..., max_length=500)
    results_count: int = Field(default=0)
    response_time_ms: float = Field(default=0.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    api_calls_count: int = Field(default=0)
    cache_hits: int = Field(default=0)
    cache_misses: int = Field(default=0)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class ApiMetricDocument(BaseModel):
    """API metric document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    api_name: str = Field(..., max_length=100)
    endpoint: str = Field(..., max_length=500)
    response_time_ms: float = Field(default=0.0)
    status_code: int = Field(default=200)
    success: bool = Field(default=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    search_query: Optional[str] = Field(None, max_length=500)
    results_count: int = Field(default=0)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class SystemMetricDocument(BaseModel):
    """System metric document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    metric_name: str = Field(..., max_length=100)
    metric_value: float = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    meta_data: Optional[Dict[str, Any]] = Field(None)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserActivityDocument(BaseModel):
    """User activity document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    action: str = Field(..., max_length=100)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    meta_data: Optional[Dict[str, Any]] = Field(None)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class MedicationCacheDocument(BaseModel):
    """Medication cache document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    query: str = Field(..., max_length=500, unique=True)
    results: Dict[str, Any] = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    hit_count: int = Field(default=0)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class RxListDrugDocument(BaseModel):
    """RxList drug document model."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., max_length=255)
    generic_name: Optional[str] = Field(None, max_length=255)
    drug_class: Optional[str] = Field(None, max_length=255)
    common_uses: Optional[List[str]] = Field(None)
    side_effects: Optional[List[str]] = Field(None)
    dosage: Optional[str] = Field(None, max_length=500)
    warnings: Optional[List[str]] = Field(None)
    interactions: Optional[List[str]] = Field(None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
