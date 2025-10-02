"""
Tests for the medication cache functionality.
"""

import pytest
import tempfile
import os
from app.medication_cache import MedicationCache, CachedMedication
from app.models import DrugSearchResult


class TestMedicationCache:
    """Test cases for MedicationCache."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def cache(self, temp_db_path):
        """Create a cache instance with temporary database."""
        return MedicationCache(temp_db_path)
    
    @pytest.fixture
    def sample_drug_result(self):
        """Sample drug result for testing."""
        return DrugSearchResult(
            rxcui="161",
            name="Tylenol",
            generic_name="acetaminophen",
            brand_names=["Tylenol"],
            common_uses=["Pain relief", "Fever reduction"],
            drug_class="Analgesic/Antipyretic",
            source="local"
        )
    
    @pytest.fixture
    def sample_ivermectin_result(self):
        """Sample ivermectin result for testing."""
        return DrugSearchResult(
            rxcui="1373244",
            name="Ivermectin",
            generic_name="Ivermectin",
            brand_names=["Sklice", "Soolantra"],
            common_uses=["Parasitic infections", "Scabies", "Head lice"],
            drug_class="Antiparasitic",
            source="rxnorm"
        )
    
    def test_cache_initialization(self, temp_db_path):
        """Test cache database initialization."""
        cache = MedicationCache(temp_db_path)
        
        # Database should be created
        assert os.path.exists(temp_db_path)
        
        # Should have empty stats initially
        stats = cache.get_cache_stats()
        assert stats["total_medications"] == 0
        assert stats["total_searches"] == 0
    
    def test_cache_medication(self, cache, sample_drug_result):
        """Test caching a single medication."""
        success = cache.cache_medication(sample_drug_result)
        assert success
        
        # Check that it was cached
        stats = cache.get_cache_stats()
        assert stats["total_medications"] == 1
        
        # Retrieve the cached medication
        retrieved = cache.get_medication(sample_drug_result.rxcui)
        assert retrieved is not None
        assert retrieved.name == sample_drug_result.name
        assert retrieved.generic_name == sample_drug_result.generic_name
        assert retrieved.brand_names == sample_drug_result.brand_names
        assert retrieved.common_uses == sample_drug_result.common_uses
        assert retrieved.drug_class == sample_drug_result.drug_class
        assert retrieved.source == sample_drug_result.source
    
    def test_cache_medications_batch(self, cache, sample_drug_result, sample_ivermectin_result):
        """Test caching multiple medications at once."""
        medications = [sample_drug_result, sample_ivermectin_result]
        cached_count = cache.cache_medications(medications)
        
        assert cached_count == 2
        
        # Check stats
        stats = cache.get_cache_stats()
        assert stats["total_medications"] == 2
        
        # Verify both medications are cached
        tylenol = cache.get_medication("161")
        ivermectin = cache.get_medication("1373244")
        
        assert tylenol is not None
        assert ivermectin is not None
        assert tylenol.name == "Tylenol"
        assert ivermectin.name == "Ivermectin"
    
    def test_search_medications_exact_match(self, cache, sample_drug_result, sample_ivermectin_result):
        """Test searching for exact medication matches."""
        # Cache both medications
        cache.cache_medications([sample_drug_result, sample_ivermectin_result])
        
        # Search for exact match
        results = cache.search_medications("tylenol", 5)
        assert len(results) == 1
        assert results[0].name == "Tylenol"
        
        # Search for generic name
        results = cache.search_medications("acetaminophen", 5)
        assert len(results) == 1
        assert results[0].name == "Tylenol"
        
        # Search for ivermectin
        results = cache.search_medications("ivermectin", 5)
        assert len(results) == 1
        assert results[0].name == "Ivermectin"
    
    def test_search_medications_partial_match(self, cache, sample_drug_result, sample_ivermectin_result):
        """Test searching for partial medication matches."""
        # Cache both medications
        cache.cache_medications([sample_drug_result, sample_ivermectin_result])
        
        # Search for partial match
        results = cache.search_medications("tyl", 5)
        assert len(results) == 1
        assert results[0].name == "Tylenol"
        
        # Search for partial match in generic name
        results = cache.search_medications("acet", 5)
        assert len(results) == 1
        assert results[0].name == "Tylenol"
        
        # Search for partial match in ivermectin
        results = cache.search_medications("iver", 5)
        assert len(results) == 1
        assert results[0].name == "Ivermectin"
    
    def test_search_medications_no_match(self, cache, sample_drug_result):
        """Test searching when no medications match."""
        cache.cache_medication(sample_drug_result)
        
        # Search for non-existent medication
        results = cache.search_medications("nonexistent", 5)
        assert len(results) == 0
        
        # Search with too short query
        results = cache.search_medications("a", 5)
        assert len(results) == 0
    
    def test_search_count_tracking(self, cache, sample_drug_result):
        """Test that search counts are tracked correctly."""
        cache.cache_medication(sample_drug_result)
        
        # Initial search
        results = cache.search_medications("tylenol", 5)
        assert len(results) == 1
        
        # Check stats
        stats = cache.get_cache_stats()
        assert stats["total_searches"] == 1
        assert stats["top_searched"][0]["name"] == "Tylenol"
        assert stats["top_searched"][0]["count"] == 1
        
        # Search again
        results = cache.search_medications("tylenol", 5)
        assert len(results) == 1
        
        # Check updated stats
        stats = cache.get_cache_stats()
        assert stats["total_searches"] == 2
        assert stats["top_searched"][0]["count"] == 2
    
    def test_cache_staleness_check(self, cache, sample_drug_result):
        """Test cache staleness checking."""
        cache.cache_medication(sample_drug_result)
        
        # Should not be stale immediately
        assert not cache.is_cache_stale(sample_drug_result.rxcui, max_age_hours=24)
        
        # Should be stale for very short age
        assert cache.is_cache_stale(sample_drug_result.rxcui, max_age_hours=0)
        
        # Non-existent medication should be considered stale
        assert cache.is_cache_stale("nonexistent", max_age_hours=24)
    
    def test_clear_cache(self, cache, sample_drug_result, sample_ivermectin_result):
        """Test clearing the cache."""
        # Cache some medications
        cache.cache_medications([sample_drug_result, sample_ivermectin_result])
        
        # Verify they're cached
        stats = cache.get_cache_stats()
        assert stats["total_medications"] == 2
        
        # Clear cache
        success = cache.clear_cache()
        assert success
        
        # Verify cache is empty
        stats = cache.get_cache_stats()
        assert stats["total_medications"] == 0
        assert stats["total_searches"] == 0
        
        # Verify medications are no longer retrievable
        tylenol = cache.get_medication("161")
        ivermectin = cache.get_medication("1373244")
        assert tylenol is None
        assert ivermectin is None
    
    def test_cache_replacement(self, cache, sample_drug_result):
        """Test that caching the same medication replaces the old entry."""
        # Cache initial medication
        cache.cache_medication(sample_drug_result)
        
        # Create updated version
        updated_result = DrugSearchResult(
            rxcui=sample_drug_result.rxcui,
            name=sample_drug_result.name,
            generic_name=sample_drug_result.generic_name,
            brand_names=sample_drug_result.brand_names,
            common_uses=["Pain relief", "Fever reduction", "Headache"],  # Updated
            drug_class=sample_drug_result.drug_class,
            source=sample_drug_result.source
        )
        
        # Cache updated version
        cache.cache_medication(updated_result)
        
        # Verify only one entry exists
        stats = cache.get_cache_stats()
        assert stats["total_medications"] == 1
        
        # Verify updated version is stored
        retrieved = cache.get_medication(sample_drug_result.rxcui)
        assert retrieved.common_uses == ["Pain relief", "Fever reduction", "Headache"]
    
    def test_search_limit(self, cache):
        """Test that search respects the limit parameter."""
        # Create multiple test medications
        medications = []
        for i in range(10):
            med = DrugSearchResult(
                rxcui=f"test_{i}",
                name=f"Test Drug {i}",
                generic_name=f"test_drug_{i}",
                brand_names=[],
                common_uses=["Test use"],
                drug_class="Test class",
                source="test"
            )
            medications.append(med)
        
        cache.cache_medications(medications)
        
        # Search with limit
        results = cache.search_medications("test", 5)
        assert len(results) <= 5
        
        # Search with different limit
        results = cache.search_medications("test", 3)
        assert len(results) <= 3
