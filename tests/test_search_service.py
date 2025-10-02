"""
Tests for the medication search service.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from app.search_service import MedicationSearchService
from app.models import DrugSearchResult


class TestMedicationSearchService:
    """Test cases for MedicationSearchService."""
    
    @pytest.fixture
    def search_service(self):
        """Create a search service instance for testing."""
        return MedicationSearchService()
    
    @pytest.fixture
    def sample_drug_results(self):
        """Sample drug results for testing."""
        return [
            DrugSearchResult(
                rxcui="1373244",
                name="ivermectin 0.8 MG/ML Oral Solution [Privermectin]",
                generic_name="ivermectin 0.8 MG/ML Oral Solution [Privermectin]",
                brand_names=["Privermectin"],
                common_uses=["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"],
                drug_class=None,
                source="rxnorm"
            ),
            DrugSearchResult(
                rxcui="199998",
                name="ivermectin 6 MG Oral Tablet",
                generic_name="ivermectin 6 MG Oral Tablet",
                brand_names=[],
                common_uses=["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"],
                drug_class=None,
                source="rxnorm"
            ),
            DrugSearchResult(
                rxcui="1246673",
                name="ivermectin 5 MG/ML Topical Lotion",
                generic_name="ivermectin 5 MG/ML Topical Lotion",
                brand_names=["Sklice"],
                common_uses=["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"],
                drug_class=None,
                source="rxnorm"
            ),
            DrugSearchResult(
                rxcui="161",
                name="Tylenol",
                generic_name="acetaminophen",
                brand_names=["Tylenol"],
                common_uses=["Pain relief", "Fever reduction"],
                drug_class="Analgesic/Antipyretic",
                source="local"
            )
        ]
    
    def test_extract_base_drug_name(self, search_service):
        """Test base drug name extraction."""
        # Test ivermectin extraction
        assert search_service._extract_base_drug_name("ivermectin 6 MG Oral Tablet") == "Ivermectin"
        assert search_service._extract_base_drug_name("ivermectin 0.8 MG/ML Oral Solution [Privermectin]") == "Ivermectin"
        assert search_service._extract_base_drug_name("ivermectin 5 MG/ML Topical Lotion") == "Ivermectin"
        
        # Test other medications
        assert search_service._extract_base_drug_name("acetaminophen 500 MG Oral Tablet") == "Acetaminophen"
        assert search_service._extract_base_drug_name("ibuprofen 200 MG Oral Capsule") == "Ibuprofen"
        assert search_service._extract_base_drug_name("atorvastatin 20 MG Oral Tablet") == "Atorvastatin"
        
        # Test edge cases
        assert search_service._extract_base_drug_name("aspirin") == "Aspirin"
        assert search_service._extract_base_drug_name("") == ""
    
    def test_consolidate_medications(self, search_service, sample_drug_results):
        """Test medication consolidation logic."""
        # Test with ivermectin results (should consolidate)
        ivermectin_results = [r for r in sample_drug_results if "ivermectin" in r.name.lower()]
        consolidated = search_service._consolidate_medications(ivermectin_results)
        
        # Should have 1 consolidated result
        assert len(consolidated) == 1
        
        consolidated_result = consolidated[0]
        assert consolidated_result.name == "Ivermectin"
        assert consolidated_result.generic_name == "Ivermectin"
        assert "Privermectin" in consolidated_result.brand_names
        assert "Sklice" in consolidated_result.brand_names
        assert consolidated_result.common_uses == ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"]
        
        # Test with mixed results (should not consolidate)
        mixed_results = sample_drug_results
        consolidated_mixed = search_service._consolidate_medications(mixed_results)
        
        # Should have 2 results (ivermectin consolidated, tylenol separate)
        assert len(consolidated_mixed) == 2
        
        # Find the consolidated ivermectin result
        ivermectin_result = next((r for r in consolidated_mixed if r.name == "Ivermectin"), None)
        assert ivermectin_result is not None
        
        # Find the tylenol result
        tylenol_result = next((r for r in consolidated_mixed if r.name == "Tylenol"), None)
        assert tylenol_result is not None
        assert tylenol_result.common_uses == ["Pain relief", "Fever reduction"]
    
    def test_merge_medications(self, search_service, sample_drug_results):
        """Test medication merging logic."""
        # Test merging ivermectin medications
        ivermectin_results = [r for r in sample_drug_results if "ivermectin" in r.name.lower()]
        merged = search_service._merge_medications(ivermectin_results)
        
        assert merged.name == "Ivermectin"
        assert merged.generic_name == "Ivermectin"
        assert "Privermectin" in merged.brand_names
        assert "Sklice" in merged.brand_names
        assert len(merged.brand_names) == 2  # Privermectin and Sklice
        assert merged.common_uses == ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"]
        
        # Test with single medication
        single_result = search_service._merge_medications([sample_drug_results[3]])  # Tylenol
        assert single_result.name == "Tylenol"
        assert single_result.generic_name == "acetaminophen"
    
    def test_sort_by_relevance(self, search_service, sample_drug_results):
        """Test relevance sorting."""
        # Test exact match gets highest priority
        results = search_service._sort_by_relevance(sample_drug_results, "ivermectin")
        assert results[0].name.lower().startswith("ivermectin")
        
        # Test partial match
        results = search_service._sort_by_relevance(sample_drug_results, "iver")
        assert results[0].name.lower().startswith("ivermectin")
        
        # Test brand name match
        results = search_service._sort_by_relevance(sample_drug_results, "tylenol")
        assert results[0].name == "Tylenol"
    
    def test_get_common_uses(self, search_service):
        """Test common uses mapping."""
        # Test specific drug mappings
        assert search_service._get_common_uses("ivermectin", "123") == ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"]
        assert search_service._get_common_uses("acetaminophen", "161") == ["Pain relief", "Fever reduction"]
        assert search_service._get_common_uses("ibuprofen", "5640") == ["Pain relief", "Inflammation", "Fever reduction"]
        assert search_service._get_common_uses("atorvastatin", "617312") == ["High cholesterol", "Cardiovascular disease prevention"]
        
        # Test pattern-based detection
        assert search_service._get_common_uses("simvastatin", "123") == ["High cholesterol", "Cardiovascular disease prevention"]
        assert search_service._get_common_uses("lisinopril", "123") == ["High blood pressure", "Heart conditions"]
        assert search_service._get_common_uses("amoxicillin", "123") == ["Bacterial infections"]
        
        # Test fallback
        assert search_service._get_common_uses("unknown_drug", "123") == ["Medication"]
    
    def test_determine_drug_class(self, search_service):
        """Test drug class determination."""
        # Test specific patterns
        assert search_service._determine_drug_class("atorvastatin") == "HMG-CoA Reductase Inhibitor (Statin)"
        assert search_service._determine_drug_class("simvastatin") == "HMG-CoA Reductase Inhibitor (Statin)"
        assert search_service._determine_drug_class("lisinopril") == "ACE Inhibitor"
        assert search_service._determine_drug_class("ibuprofen") == "NSAID (Non-steroidal Anti-inflammatory)"
        assert search_service._determine_drug_class("omeprazole") == "Proton Pump Inhibitor (PPI)"
        
        # Test fallback
        assert search_service._determine_drug_class("unknown_drug") is None
    
    @pytest.mark.asyncio
    async def test_search_medications_empty_query(self, search_service):
        """Test search with empty query."""
        results = await search_service.search_medications("")
        assert results == []
        
        results = await search_service.search_medications("a")
        assert results == []
    
    @pytest.mark.asyncio
    async def test_search_medications_local_fallback(self, search_service):
        """Test local fallback search."""
        # Mock the cache to return empty results
        with patch.object(search_service._medication_cache, 'search_medications', return_value=[]):
            results = await search_service.search_medications("tyl", 5)
            
            # Should find Tylenol from local fallback
            assert len(results) > 0
            assert any("tylenol" in result.name.lower() for result in results)
    
    @pytest.mark.asyncio
    async def test_search_medications_caching(self, search_service):
        """Test that results are cached."""
        # Mock RxNorm API to return sample results
        mock_api_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = {
            "drugGroup": {
                "conceptGroup": [
                    {
                        "tty": "BN",
                        "conceptProperties": [
                            {"rxcui": "123", "name": "Test Drug", "synonym": "Test Drug"}
                        ]
                    }
                ]
            }
        }
        mock_response.status_code = 200
        mock_api_client.http_client.get.return_value = mock_response
        
        with patch('app.search_service.get_medical_api_client', return_value=mock_api_client):
            with patch.object(search_service._medication_cache, 'search_medications', return_value=[]):
                with patch.object(search_service._medication_cache, 'cache_medications') as mock_cache:
                    results = await search_service.search_medications("test", 5)
                    
                    # Should cache the results
                    mock_cache.assert_called_once()
    
    def test_search_local_drugs(self, search_service):
        """Test local drug search functionality."""
        # Test exact match
        results = search_service._search_local_drugs("tylenol", 5)
        assert len(results) > 0
        assert any("tylenol" in result.name.lower() for result in results)
        
        # Test partial match
        results = search_service._search_local_drugs("tyl", 5)
        assert len(results) > 0
        assert any("tylenol" in result.name.lower() for result in results)
        
        # Test no match
        results = search_service._search_local_drugs("nonexistent", 5)
        assert len(results) == 0
        
        # Test short query
        results = search_service._search_local_drugs("a", 5)
        assert len(results) == 0
