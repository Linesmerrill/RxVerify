"""Build or refresh vector embeddings for the normalized docs table."""
import asyncio
from app.embeddings import embed
from app.db import execute

async def reindex(batch_size: int = 256):
    # 1) SELECT id, text FROM docs WHERE embedding IS NULL LIMIT :batch
    # 2) embed(texts) -> vectors
    # 3) UPDATE docs SET embedding = :vec WHERE id = :id
    pass

if __name__ == "__main__":
    asyncio.run(reindex())
