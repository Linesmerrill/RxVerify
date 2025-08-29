from typing import List

# Replace with OpenAI, Azure OpenAI, or local embeddings
async def embed(texts: List[str]) -> List[List[float]]:
    # ChromaDB's default model (all-MiniLM-L6-v2) produces 384-dimensional vectors
    # return [[0.0]*384 for _ in texts]  # stub dims
    return [[0.001 * (i+1) for i in range(384)] for _ in texts]
