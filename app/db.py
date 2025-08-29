import os
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings

# ChromaDB client - uses local file storage by default
client = chromadb.PersistentClient(path="./chroma_db")

# Get or create collection for drug documents
def get_collection():
    try:
        return client.get_collection("drug_docs")
    except:
        return client.create_collection(
            "drug_docs",
            metadata={"hnsw:space": "cosine"}  # Better for text similarity
        )

def search_keyword(query: str, limit: int = 10) -> List[dict]:
    """Search by text content using ChromaDB's text search."""
    collection = get_collection()
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["metadatas", "documents", "distances"]
    )
    
    docs = []
    if results['documents']:
        for i, doc in enumerate(results['documents'][0]):
            docs.append({
                "text": doc,
                "metadata": results['metadatas'][0][i],
                "score": 1.0 - results['distances'][0][i]  # Convert distance to similarity score
            })
    return docs

def search_vector(embedding: list[float], limit: int = 10) -> List[dict]:
    """Search by vector similarity using ChromaDB."""
    collection = get_collection()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=limit,
        include=["metadatas", "documents", "distances"]
    )
    
    docs = []
    if results['documents']:
        for i, doc in enumerate(results['documents'][0]):
            docs.append({
                "text": doc,
                "metadata": results['metadatas'][0][i],
                "score": 1.0 - results['distances'][0][i]  # Convert distance to similarity score
            })
    return docs

async def add_document(rxcui: Optional[str], source: str, id: str, url: Optional[str], 
                 title: Optional[str], text: str, embedding: Optional[List[float]] = None):
    """Add a document to the ChromaDB collection."""
    collection = get_collection()
    
    metadata = {
        "rxcui": rxcui,
        "source": source,
        "id": id,
        "url": url,
        "title": title
    }
    
    collection.add(
        documents=[text],
        metadatas=[metadata],
        ids=[f"{source}_{id}"],
        embeddings=[embedding] if embedding else None
    )
