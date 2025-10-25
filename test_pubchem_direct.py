#!/usr/bin/env python3
"""Quick test to see if PubChem API is working."""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.medical_apis import get_medical_api_client

async def test_pubchem_direct():
    """Test PubChem API directly."""
    print("🧪 Testing PubChem API Directly")
    print("=" * 40)
    
    api_client = await get_medical_api_client()
    
    try:
        # Test PubChem search directly
        results = await api_client.search_pubchem("acetazolamide", limit=3)
        
        if results:
            print(f"✅ PubChem found {len(results)} results:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result.get('title', 'Unknown')}")
                print(f"     URL: {result.get('url', 'N/A')}")
        else:
            print("❌ No results from PubChem")
            
    except Exception as e:
        print(f"❌ PubChem error: {e}")
    
    await api_client.close()

if __name__ == "__main__":
    asyncio.run(test_pubchem_direct())
