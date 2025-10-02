#!/usr/bin/env python3
"""
Manual test script to verify medication search functionality.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.search_service import MedicationSearchService
from app.medication_cache import MedicationCache
from app.models import DrugSearchResult

def test_extract_base_drug_name():
    """Test base drug name extraction."""
    print("🧪 Testing base drug name extraction...")
    
    service = MedicationSearchService()
    
    test_cases = [
        ("ivermectin 6 MG Oral Tablet", "Ivermectin"),
        ("ivermectin 0.8 MG/ML Oral Solution [Privermectin]", "Ivermectin"),
        ("acetaminophen 500 MG Oral Tablet", "Acetaminophen"),
        ("ibuprofen 200 MG Oral Capsule", "Ibuprofen"),
        ("aspirin", "Aspirin"),
    ]
    
    for input_name, expected in test_cases:
        result = service._extract_base_drug_name(input_name)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{input_name}' -> '{result}' (expected: '{expected}')")
    
    print()

def test_consolidation():
    """Test medication consolidation."""
    print("🧪 Testing medication consolidation...")
    
    service = MedicationSearchService()
    
    # Create sample ivermectin results
    ivermectin_results = [
        DrugSearchResult(
            rxcui="1373244",
            name="ivermectin 0.8 MG/ML Oral Solution [Privermectin]",
            generic_name="ivermectin 0.8 MG/ML Oral Solution [Privermectin]",
            brand_names=["Privermectin"],
            common_uses=["Parasitic infections", "Scabies", "Head lice"],
            drug_class=None,
            source="rxnorm"
        ),
        DrugSearchResult(
            rxcui="199998",
            name="ivermectin 6 MG Oral Tablet",
            generic_name="ivermectin 6 MG Oral Tablet",
            brand_names=[],
            common_uses=["Parasitic infections", "Scabies", "Head lice"],
            drug_class=None,
            source="rxnorm"
        ),
        DrugSearchResult(
            rxcui="1246673",
            name="ivermectin 5 MG/ML Topical Lotion",
            generic_name="ivermectin 5 MG/ML Topical Lotion",
            brand_names=["Sklice"],
            common_uses=["Parasitic infections", "Scabies", "Head lice"],
            drug_class=None,
            source="rxnorm"
        )
    ]
    
    # Test consolidation
    consolidated = service._consolidate_medications(ivermectin_results)
    
    print(f"  Input: {len(ivermectin_results)} ivermectin results")
    print(f"  Output: {len(consolidated)} consolidated results")
    
    if len(consolidated) == 1:
        result = consolidated[0]
        print(f"  ✅ Consolidated name: '{result.name}'")
        print(f"  ✅ Brand names: {result.brand_names}")
        print(f"  ✅ Common uses: {result.common_uses}")
    else:
        print(f"  ❌ Expected 1 result, got {len(consolidated)}")
    
    print()

def test_common_uses():
    """Test common uses mapping."""
    print("🧪 Testing common uses mapping...")
    
    service = MedicationSearchService()
    
    test_cases = [
        ("ivermectin", ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"]),
        ("acetaminophen", ["Pain relief", "Fever reduction"]),
        ("ibuprofen", ["Pain relief", "Inflammation", "Fever reduction"]),
        ("atorvastatin", ["High cholesterol", "Cardiovascular disease prevention"]),
    ]
    
    for drug_name, expected_uses in test_cases:
        result = service._get_common_uses(drug_name, "123")
        status = "✅" if result == expected_uses else "❌"
        print(f"  {status} '{drug_name}' -> {result}")
        if result != expected_uses:
            print(f"    Expected: {expected_uses}")
    
    print()

async def test_search_service():
    """Test search service functionality."""
    print("🧪 Testing search service...")
    
    service = MedicationSearchService()
    
    # Test local search
    print("  Testing local search...")
    local_results = service._search_local_drugs("tyl", 5)
    if local_results:
        print(f"  ✅ Found {len(local_results)} local results for 'tyl'")
        for result in local_results:
            print(f"    - {result.name} ({result.generic_name})")
    else:
        print("  ❌ No local results found for 'tyl'")
    
    print()

def test_cache():
    """Test medication cache functionality."""
    print("🧪 Testing medication cache...")
    
    # Create temporary cache
    cache = MedicationCache("test_cache.db")
    
    # Test caching
    test_drug = DrugSearchResult(
        rxcui="161",
        name="Tylenol",
        generic_name="acetaminophen",
        brand_names=["Tylenol"],
        common_uses=["Pain relief", "Fever reduction"],
        drug_class="Analgesic/Antipyretic",
        source="local"
    )
    
    # Cache the drug
    success = cache.cache_medication(test_drug)
    print(f"  {'✅' if success else '❌'} Cached medication: {test_drug.name}")
    
    # Search for it
    results = cache.search_medications("tylenol", 5)
    print(f"  {'✅' if results else '❌'} Found {len(results)} cached results")
    
    # Get stats
    stats = cache.get_cache_stats()
    print(f"  ✅ Cache stats: {stats['total_medications']} medications, {stats['total_searches']} searches")
    
    # Cleanup
    cache.clear_cache()
    os.remove("test_cache.db")
    
    print()

def main():
    """Run all manual tests."""
    print("🚀 RxVerify Manual Test Suite")
    print("=" * 50)
    
    try:
        test_extract_base_drug_name()
        test_consolidation()
        test_common_uses()
        asyncio.run(test_search_service())
        test_cache()
        
        print("🎉 All manual tests completed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
