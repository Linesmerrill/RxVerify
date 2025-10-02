#!/usr/bin/env python3
"""
Simple test to verify basic functionality without dependencies.
"""

import re

def test_extract_base_drug_name():
    """Test base drug name extraction logic."""
    print("🧪 Testing base drug name extraction...")
    
    def extract_base_drug_name(full_name):
        """Extract the base drug name from a full medication name."""
        # Remove common suffixes and dosage information
        name = full_name.lower()
        
        # Remove dosage patterns (more comprehensive)
        name = re.sub(r'\d+\s*(mg|mcg|g|ml|%|mg/ml|mcg/ml)\s*', '', name)
        name = re.sub(r'\s*(oral|topical|injection|cream|lotion|tablet|solution|capsule|gel|drops|spray|patch)\s*', '', name)
        name = re.sub(r'\[.*?\]', '', name)  # Remove bracketed text
        name = re.sub(r'\(.*?\)', '', name)  # Remove parenthetical text
        name = re.sub(r'\s+', ' ', name).strip()  # Clean up spaces
        
        # If we have multiple words, take the first meaningful word
        words = name.split()
        if words:
            # Take the first word that looks like a drug name (not empty, not just numbers/symbols)
            for word in words:
                if word and not re.match(r'^[\d\.\-\/]+$', word):
                    return word.capitalize()
        
        # Fallback to original name if extraction fails
        return full_name
    
    test_cases = [
        ("ivermectin 6 MG Oral Tablet", "Ivermectin"),
        ("ivermectin 0.8 MG/ML Oral Solution [Privermectin]", "Ivermectin"),
        ("acetaminophen 500 MG Oral Tablet", "Acetaminophen"),
        ("ibuprofen 200 MG Oral Capsule", "Ibuprofen"),
        ("aspirin", "Aspirin"),
        ("tylenol", "Tylenol"),
    ]
    
    all_passed = True
    for input_name, expected in test_cases:
        result = extract_base_drug_name(input_name)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{input_name}' -> '{result}' (expected: '{expected}')")
        if result != expected:
            all_passed = False
    
    print(f"\n  Result: {'✅ All tests passed!' if all_passed else '❌ Some tests failed!'}")
    return all_passed

def test_consolidation_logic():
    """Test medication consolidation logic."""
    print("\n🧪 Testing medication consolidation logic...")
    
    # Simulate medication results with same common uses
    medications = [
        {
            "rxcui": "1373244",
            "name": "ivermectin 0.8 MG/ML Oral Solution [Privermectin]",
            "brand_names": ["Privermectin"],
            "common_uses": ["Parasitic infections", "Scabies", "Head lice"]
        },
        {
            "rxcui": "199998", 
            "name": "ivermectin 6 MG Oral Tablet",
            "brand_names": [],
            "common_uses": ["Parasitic infections", "Scabies", "Head lice"]
        },
        {
            "rxcui": "1246673",
            "name": "ivermectin 5 MG/ML Topical Lotion", 
            "brand_names": ["Sklice"],
            "common_uses": ["Parasitic infections", "Scabies", "Head lice"]
        }
    ]
    
    # Group by common uses
    groups = {}
    for med in medications:
        uses_key = tuple(sorted(med["common_uses"]))
        if uses_key not in groups:
            groups[uses_key] = []
        groups[uses_key].append(med)
    
    print(f"  Input: {len(medications)} medications")
    print(f"  Groups: {len(groups)} groups by common uses")
    
    # Check consolidation
    if len(groups) == 1:
        group = list(groups.values())[0]
        print(f"  ✅ All medications have same common uses: {group[0]['common_uses']}")
        
        # Collect all brand names
        all_brands = set()
        for med in group:
            all_brands.update(med["brand_names"])
        
        print(f"  ✅ Consolidated brand names: {list(all_brands)}")
        print(f"  ✅ Would consolidate {len(group)} medications into 1 result")
        return True
    else:
        print(f"  ❌ Expected 1 group, got {len(groups)}")
        return False

def test_common_uses_mapping():
    """Test common uses mapping logic."""
    print("\n🧪 Testing common uses mapping...")
    
    # Simulate common uses mapping
    common_uses_map = {
        "ivermectin": ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"],
        "acetaminophen": ["Pain relief", "Fever reduction"],
        "ibuprofen": ["Pain relief", "Inflammation", "Fever reduction"],
        "atorvastatin": ["High cholesterol", "Cardiovascular disease prevention"],
    }
    
    def get_common_uses(drug_name):
        name_lower = drug_name.lower()
        
        # Check for exact matches
        if name_lower in common_uses_map:
            return common_uses_map[name_lower]
        
        # Check for partial matches
        for key, uses in common_uses_map.items():
            if key in name_lower or name_lower in key:
                return uses
        
        # Pattern-based detection
        if "statin" in name_lower or "vastatin" in name_lower:
            return ["High cholesterol", "Cardiovascular disease prevention"]
        elif "mectin" in name_lower or "vermectin" in name_lower:
            return ["Parasitic infections", "Scabies", "Head lice"]
        elif "profen" in name_lower:
            return ["Pain relief", "Inflammation", "Fever reduction"]
        
        return ["Medication"]
    
    test_cases = [
        ("ivermectin", ["Parasitic infections", "Scabies", "Head lice", "River blindness", "Strongyloidiasis"]),
        ("acetaminophen", ["Pain relief", "Fever reduction"]),
        ("ibuprofen", ["Pain relief", "Inflammation", "Fever reduction"]),
        ("atorvastatin", ["High cholesterol", "Cardiovascular disease prevention"]),
        ("simvastatin", ["High cholesterol", "Cardiovascular disease prevention"]),  # Pattern-based
    ]
    
    all_passed = True
    for drug_name, expected in test_cases:
        result = get_common_uses(drug_name)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{drug_name}' -> {result}")
        if result != expected:
            print(f"    Expected: {expected}")
            all_passed = False
    
    print(f"\n  Result: {'✅ All tests passed!' if all_passed else '❌ Some tests failed!'}")
    return all_passed

def main():
    """Run all simple tests."""
    print("🚀 RxVerify Simple Test Suite")
    print("=" * 50)
    
    test1 = test_extract_base_drug_name()
    test2 = test_consolidation_logic()
    test3 = test_common_uses_mapping()
    
    print("\n" + "=" * 50)
    if test1 and test2 and test3:
        print("🎉 All simple tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
