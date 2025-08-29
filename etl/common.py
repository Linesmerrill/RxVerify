from typing import Iterable, Dict
from app.db import add_document
from app.embeddings import embed

# Map a source record to RxCUI using RxNorm data you load separately.
def map_to_rxcui(record: Dict) -> str | None:
    # TODO: implement lookup via RXNORM tables
    return record.get("rxcui")

async def upsert_doc(rxcui: str | None, source: str, id: str, url: str | None, title: str | None, text: str):
    """Insert or update a document in ChromaDB for retrieval."""
    # Generate embedding for the text
    embedding = (await embed([text]))[0]
    
    # Add to ChromaDB collection
    await add_document(
        rxcui=rxcui,
        source=source,
        id=id,
        url=url,
        title=title,
        text=text,
        embedding=embedding
    )
