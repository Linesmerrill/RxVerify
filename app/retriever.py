from typing import List
from app.db import search_keyword, search_vector
from app.embeddings import embed
from app.models import RetrievedDoc, Source

async def retrieve(question: str, top_k: int = 6) -> List[RetrievedDoc]:
    # 1) Hybrid search: vector + keyword
    vec = (await embed([question]))[0]
    v_hits = search_vector(vec, limit=top_k)
    k_hits = search_keyword(question, limit=top_k)

    # 2) Normalize to RetrievedDoc from ChromaDB results
    docs = []
    for hit in v_hits + k_hits:
        # Map source string to Source enum
        source_str = hit["metadata"]["source"]
        try:
            source = Source(source_str)
        except ValueError:
            # Skip invalid sources
            continue
            
        docs.append(RetrievedDoc(
            rxcui=hit["metadata"]["rxcui"],
            source=source,
            id=hit["metadata"]["id"],
            url=hit["metadata"]["url"],
            title=hit["metadata"]["title"],
            text=hit["text"],
            score=hit["score"]
        ))

    # 3) De‑dupe by (source,id) and keep best score
    seen = {}
    out = []
    for d in sorted(docs, key=lambda x: x.score, reverse=True):
        key = (d.source, d.id)
        if key in seen:
            continue
        seen[key] = True
        out.append(d)
    return out[:top_k]
