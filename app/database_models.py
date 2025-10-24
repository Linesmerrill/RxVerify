"""
SQLAlchemy Database Models
Defines all database tables for persistent storage
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class FeedbackEntry(Base):
    """Feedback entries table."""
    __tablename__ = "feedback_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    drug_name = Column(String(255), nullable=False, index=True)
    query = Column(String(500), nullable=False, index=True)
    is_positive = Column(Boolean, nullable=False, default=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    user_id = Column(String(100), nullable=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    
    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_drug_query', 'drug_name', 'query'),
        Index('idx_timestamp_user', 'timestamp', 'user_id'),
    )

class SearchMetric(Base):
    """Search metrics table."""
    __tablename__ = "search_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    query = Column(String(500), nullable=False, index=True)
    results_count = Column(Integer, default=0)
    response_time_ms = Column(Float, default=0.0)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    user_id = Column(String(100), nullable=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    api_calls_count = Column(Integer, default=0)
    cache_hits = Column(Integer, default=0)
    cache_misses = Column(Integer, default=0)
    
    # Composite indexes
    __table_args__ = (
        Index('idx_query_timestamp', 'query', 'timestamp'),
        Index('idx_user_timestamp', 'user_id', 'timestamp'),
    )

class ApiMetric(Base):
    """API call metrics table."""
    __tablename__ = "api_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    api_name = Column(String(100), nullable=False, index=True)
    endpoint = Column(String(500), nullable=False)
    response_time_ms = Column(Float, default=0.0)
    status_code = Column(Integer, default=200)
    success = Column(Boolean, default=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    search_query = Column(String(500), nullable=True, index=True)
    results_count = Column(Integer, default=0)
    
    # Composite indexes
    __table_args__ = (
        Index('idx_api_timestamp', 'api_name', 'timestamp'),
        Index('idx_success_timestamp', 'success', 'timestamp'),
    )

class SystemMetric(Base):
    """System performance metrics table."""
    __tablename__ = "system_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    metadata = Column(Text, nullable=True)
    
    # Composite index
    __table_args__ = (
        Index('idx_metric_timestamp', 'metric_name', 'timestamp'),
    )

class UserActivity(Base):
    """User activity tracking table."""
    __tablename__ = "user_activity"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), nullable=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    metadata = Column(Text, nullable=True)
    
    # Composite indexes
    __table_args__ = (
        Index('idx_user_action', 'user_id', 'action'),
        Index('idx_session_timestamp', 'session_id', 'timestamp'),
    )

class MedicationCache(Base):
    """Medication cache table."""
    __tablename__ = "medication_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    query = Column(String(500), nullable=False, unique=True, index=True)
    results = Column(Text, nullable=False)  # JSON string
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    hit_count = Column(Integer, default=0)
    
    # Index for efficient cache lookups
    __table_args__ = (
        Index('idx_query_timestamp', 'query', 'timestamp'),
    )

class RxListDrug(Base):
    """RxList drugs table."""
    __tablename__ = "rxlist_drugs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    generic_name = Column(String(255), nullable=True, index=True)
    drug_class = Column(String(255), nullable=True, index=True)
    common_uses = Column(Text, nullable=True)
    side_effects = Column(Text, nullable=True)
    dosage = Column(String(500), nullable=True)
    warnings = Column(Text, nullable=True)
    interactions = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    
    # Composite indexes
    __table_args__ = (
        Index('idx_name_generic', 'name', 'generic_name'),
        Index('idx_drug_class', 'drug_class'),
    )
