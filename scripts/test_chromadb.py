#!/usr/bin/env python3
"""Test script to verify ChromaDB setup and basic operations."""

import asyncio
import sys
import os

# Add the parent directory to the path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import add_document, search_keyword, search_vector
from app.embeddings import embed

async def test_chromadb():
    """Test basic ChromaDB operations."""
    print("🧪 Testing ChromaDB setup...")
    
    # Test document addition
    print("📝 Adding test documents...")
    await add_document(
        rxcui="12345",
        source="rxnorm",
        id="test_1",
        url="https://example.com",
        title="Atorvastatin",
        text="Atorvastatin is a statin medication used to treat high cholesterol and prevent cardiovascular disease."
    )
    
    await add_document(
        rxcui="12345",
        source="dailymed",
        id="test_2", 
        url="https://dailymed.nlm.nih.gov",
        title="Atorvastatin Calcium",
        text="Atorvastatin calcium tablets are indicated for the treatment of elevated total cholesterol, LDL-C, triglycerides, and to increase HDL-C."
    )
    
    print("✅ Documents added successfully!")
    
    # Test search
    print("\n🔍 Testing search functionality...")
    
    # Keyword search
    keyword_results = search_keyword("cholesterol", limit=5)
    print(f"Keyword search found {len(keyword_results)} results")
    
    # Vector search
    query_embedding = (await embed(["cholesterol medication"]))[0]
    vector_results = search_vector(query_embedding, limit=5)
    print(f"Vector search found {len(vector_results)} results")
    
    print("✅ Search functionality working!")
    
    # Show results
    print("\n📊 Sample results:")
    for i, result in enumerate(keyword_results[:2]):
        print(f"  {i+1}. {result['metadata']['title']} ({result['metadata']['source']})")
        print(f"     Score: {result['score']:.3f}")
        print(f"     Text: {result['text'][:100]}...")
    
    print("\n🎉 ChromaDB test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_chromadb())
