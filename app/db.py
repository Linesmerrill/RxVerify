import os
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from app.embeddings import embed
from app.config import settings
import asyncio

# ChromaDB client - adapts to environment (local vs Heroku)
def get_chromadb_client():
    """Get ChromaDB client configured for the current environment."""
    if settings.IS_HEROKU:
        # On Heroku, use in-memory client since filesystem is ephemeral
        # Data will be lost on restart, but that's acceptable for this use case
        return chromadb.Client()
    else:
        # Local development - use persistent storage
        return chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)

client = get_chromadb_client()

# Custom embedding function for ChromaDB
class ChromaEmbeddingFunction:
    def __init__(self):
        pass
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        """ChromaDB-compatible embedding function that calls our async embed function."""
        # Run the async function in a new event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(embed(input))

# Get or create collection for drug documents
def get_collection():
    try:
        return client.get_collection("drug_docs")
    except:
        return client.create_collection(
            "drug_docs",
            metadata={"hnsw:space": "l2"},  # Use Euclidean distance for better differentiation
            embedding_function=ChromaEmbeddingFunction()  # Use our custom embedding function
        )

# Initialize collection on startup
collection = get_collection()

async def search_keyword(query: str, limit: int = 10) -> List[dict]:
    """Search by text content using our custom embeddings."""
    collection = get_collection()
    
    # Generate embedding for the query using our function
    query_embedding = (await embed([query]))[0]
    
    # Search by embedding instead of text
    results = collection.query(
        query_embeddings=[query_embedding],
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
