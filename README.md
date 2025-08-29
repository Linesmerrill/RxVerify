# RxVerify: Multi-Database Drug Assistant

**Description:**
RxVerify is an open-source Retrieval-Augmented Generation (RAG) backend for drug information. It ingests data from multiple free and authoritative sources (RxNorm, DailyMed, OpenFDA, and the open subset of DrugBank), unifies them by RxCUI, and cross-checks fields to ensure accuracy and transparency. Queries are answered strictly from these trusted databases, with explicit citations and disclosure of disagreements between sources.

> ⚠️ **Disclaimer:** RxVerify is for research and educational use only. It does not provide medical advice. Always consult a licensed healthcare professional.

---

## Features

* **Multi-source ingestion** → ETL pipelines for RxNorm, DailyMed, OpenFDA, DrugBank (open)
* **Cross-checking** → Detects discrepancies between sources and reports them
* **RAG pipeline** → Vector + keyword search, unified drug records, LLM answers
* **Citations** → Inline references (e.g., \[RxNorm\:ID], \[DailyMed\:ID])
* **FastAPI backend** → Simple API endpoints for queries
* **Dockerized** → Ready to run in containers

---

## Getting Started

### Prerequisites

* Python 3.11+
* PostgreSQL with [pgvector](https://github.com/pgvector/pgvector)
* OpenAI API key (or replace with another embedding/LLM provider)

### Install

```bash
git clone https://github.com/yourname/rxverify.git
cd rxverify
cp .env.example .env
# edit your DB + API key
pip install -r requirements.txt
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

Visit: [http://localhost:8000/docs](http://localhost:8000/docs)

### Example Query

```bash
curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the recommended dose of Atorvastatin?"}'
```

---

## Project Layout

```
rxverify/
├─ app/          # FastAPI app, retrieval, cross-checking, prompts
├─ etl/          # Data ingestion for RxNorm, DailyMed, OpenFDA, DrugBank
├─ scripts/      # Utilities (e.g., embedding reindex)
├─ tests/        # Unit tests
```

---

## Roadmap

* [ ] Implement full ETL for each source
* [ ] Add structured parsing for SPL (DailyMed)
* [ ] Support Pinecone/Weaviate as alternative vector stores
* [ ] Web UI with citations & disagreement highlighting

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

* [RxNorm](https://www.nlm.nih.gov/research/umls/rxnorm/)
* [DailyMed](https://dailymed.nlm.nih.gov/)
* [OpenFDA](https://open.fda.gov/)
* [DrugBank Open Data](https://go.drugbank.com/releases/latest)

---
