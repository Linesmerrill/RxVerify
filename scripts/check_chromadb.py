#!/usr/bin/env python3
"""Script to inspect the contents of ChromaDB collection."""

import sys
import os

# Add the parent directory to the path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_collection

def check_chromadb_contents():
    """Check what's actually stored in ChromaDB."""
    print("🔍 Inspecting ChromaDB Collection Contents...")
    
    try:
        collection = get_collection()
        
        # Get collection info
        print(f"Collection: {collection.name}")
        print(f"Count: {collection.count()}")
        
        # Get all documents
        results = collection.get(
            include=["metadatas", "documents", "embeddings"]
        )
        
        if results['ids']:
            print(f"\n📚 Found {len(results['ids'])} documents:")
            print("-" * 60)
            
            for i, doc_id in enumerate(results['ids']):
                metadata = results['metadatas'][i]
                document = results['documents'][i]
                
                print(f"\nDocument {i+1}: {doc_id}")
                print(f"  Source: {metadata.get('source', 'Unknown')}")
                print(f"  RxCUI: {metadata.get('rxcui', 'Unknown')}")
                print(f"  Title: {metadata.get('title', 'Unknown')}")
                print(f"  Text Preview: {document[:100]}..." if len(document) > 100 else f"  Text: {document}")
                print(f"  Has Embedding: {'Yes' if results['embeddings'][i] else 'No'}")
                
        else:
            print("❌ No documents found in collection!")
            
    except Exception as e:
        print(f"❌ Error accessing ChromaDB: {str(e)}")

if __name__ == "__main__":
    check_chromadb_contents()
