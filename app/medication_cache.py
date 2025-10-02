"""
Medication Cache Database
Stores frequently searched medications for fast lookup and improved common uses.
"""

import sqlite3
import json
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from app.models import DrugSearchResult
from app.logging import get_logger

logger = get_logger(__name__)

@dataclass
class CachedMedication:
    """Represents a cached medication entry."""
    rxcui: str
    name: str
    generic_name: Optional[str]
    brand_names: List[str]
    common_uses: List[str]
    drug_class: Optional[str]
    last_updated: float
    search_count: int
    source: str

class MedicationCache:
    """Manages medication cache database for fast lookups."""
    
    def __init__(self, db_path: str = "medication_cache.db"):
        self.db_path = Path(db_path)
        self._init_database()
    
    def _init_database(self):
        """Initialize the medication cache database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS medications (
                        rxcui TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        generic_name TEXT,
                        brand_names TEXT,  -- JSON array
                        common_uses TEXT,  -- JSON array
                        drug_class TEXT,
                        last_updated REAL NOT NULL,
                        search_count INTEGER DEFAULT 0,
                        source TEXT NOT NULL
                    )
                """)
                
                # Create index for faster name searches
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_medications_name 
                    ON medications(name)
                """)
                
                # Create index for partial name searches
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_medications_name_lower 
                    ON medications(LOWER(name))
                """)
                
                conn.commit()
                logger.info("Medication cache database initialized")
                
        except Exception as e:
            logger.error(f"Failed to initialize medication cache database: {e}")
            raise
    
    def search_medications(self, query: str, limit: int = 10) -> List[DrugSearchResult]:
        """Search cached medications by name (exact and partial matches)."""
        if not query or len(query.strip()) < 2:
            return []
        
        query = query.strip().lower()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Search for exact matches first, then partial matches
                cursor = conn.execute("""
                    SELECT * FROM medications 
                    WHERE LOWER(name) = ? OR LOWER(generic_name) = ?
                    ORDER BY search_count DESC, last_updated DESC
                    LIMIT ?
                """, (query, query, limit))
                
                exact_matches = [self._row_to_drug_result(row) for row in cursor.fetchall()]
                
                if exact_matches:
                    # Update search count for exact matches
                    for match in exact_matches:
                        self._increment_search_count(match.rxcui)
                    return exact_matches
                
                # Search for partial matches
                cursor = conn.execute("""
                    SELECT * FROM medications 
                    WHERE LOWER(name) LIKE ? OR LOWER(generic_name) LIKE ?
                    ORDER BY search_count DESC, last_updated DESC
                    LIMIT ?
                """, (f"%{query}%", f"%{query}%", limit))
                
                partial_matches = [self._row_to_drug_result(row) for row in cursor.fetchall()]
                
                # Update search count for partial matches
                for match in partial_matches:
                    self._increment_search_count(match.rxcui)
                
                return partial_matches
                
        except Exception as e:
            logger.error(f"Failed to search cached medications: {e}")
            return []
    
    def get_medication(self, rxcui: str) -> Optional[DrugSearchResult]:
        """Get a specific medication by RxCUI."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM medications WHERE rxcui = ?", (rxcui,))
                row = cursor.fetchone()
                
                if row:
                    self._increment_search_count(rxcui)
                    return self._row_to_drug_result(row)
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get medication {rxcui}: {e}")
            return None
    
    def cache_medication(self, medication: DrugSearchResult) -> bool:
        """Cache a medication for future fast lookup."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO medications 
                    (rxcui, name, generic_name, brand_names, common_uses, drug_class, last_updated, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    medication.rxcui,
                    medication.name,
                    medication.generic_name,
                    json.dumps(medication.brand_names),
                    json.dumps(medication.common_uses),
                    medication.drug_class,
                    time.time(),
                    medication.source
                ))
                conn.commit()
                logger.debug(f"Cached medication: {medication.name} (RxCUI: {medication.rxcui})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cache medication {medication.rxcui}: {e}")
            return False
    
    def cache_medications(self, medications: List[DrugSearchResult]) -> int:
        """Cache multiple medications at once."""
        cached_count = 0
        for medication in medications:
            if self.cache_medication(medication):
                cached_count += 1
        return cached_count
    
    def _increment_search_count(self, rxcui: str):
        """Increment the search count for a medication."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE medications 
                    SET search_count = search_count + 1 
                    WHERE rxcui = ?
                """, (rxcui,))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to increment search count for {rxcui}: {e}")
    
    def _row_to_drug_result(self, row: sqlite3.Row) -> DrugSearchResult:
        """Convert database row to DrugSearchResult."""
        return DrugSearchResult(
            rxcui=row['rxcui'],
            name=row['name'],
            generic_name=row['generic_name'],
            brand_names=json.loads(row['brand_names']) if row['brand_names'] else [],
            common_uses=json.loads(row['common_uses']) if row['common_uses'] else [],
            drug_class=row['drug_class'],
            source=row['source']
        )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) as total FROM medications")
                total = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT SUM(search_count) as total_searches FROM medications")
                total_searches = cursor.fetchone()[0] or 0
                
                cursor = conn.execute("""
                    SELECT name, search_count 
                    FROM medications 
                    ORDER BY search_count DESC 
                    LIMIT 5
                """)
                top_searched = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                return {
                    "total_medications": total,
                    "total_searches": total_searches,
                    "top_searched": top_searched
                }
                
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"total_medications": 0, "total_searches": 0, "top_searched": []}
    
    def clear_cache(self) -> bool:
        """Clear all cached medications."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM medications")
                conn.commit()
                logger.info("Medication cache cleared")
                return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    def is_cache_stale(self, rxcui: str, max_age_hours: int = 24) -> bool:
        """Check if a cached medication is stale and needs updating."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT last_updated FROM medications WHERE rxcui = ?
                """, (rxcui,))
                row = cursor.fetchone()
                
                if not row:
                    return True  # Not cached, consider stale
                
                age_hours = (time.time() - row[0]) / 3600
                return age_hours > max_age_hours
                
        except Exception as e:
            logger.error(f"Failed to check cache staleness for {rxcui}: {e}")
            return True  # Assume stale on error

# Global cache instance
_cache_instance: Optional[MedicationCache] = None

def get_medication_cache() -> MedicationCache:
    """Get the global medication cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MedicationCache()
    return _cache_instance
