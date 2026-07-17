# 📘 PHC Judgment RAG System

A Retrieval-Augmented Generation (RAG) system for Peshawar High Court judgments.

The project automatically scrapes judgments, downloads PDFs, generates metadata using a free LLM, indexes the documents into Weaviate, and provides a FastAPI chat interface for semantic legal search.

---

# Features

## Data Collection

- Scrapes Peshawar High Court judgments
- Downloads judgment PDFs
- Stores structured metadata in JSON
- Prevents duplicate records

## Document Processing

- Converts PDFs to Markdown
- Chunks judgments
- Generates embeddings
- Generates metadata using Ollama (Phi-3 Mini)

Metadata includes:

- Case title
- Case number
- Court
- Judge
- Decision date
- Neutral citation
- Summary
- Keywords
- Legal issues
- Acts
- Sections
- Final decision

---

# Search Pipeline

The retrieval pipeline consists of:

```
User Query
      │
      ▼
Query Classification
      │
      ▼
Hybrid Search
(Vector + BM25)
      │
      ▼
Cross Encoder Reranker
      │
      ▼
Top Relevant Chunks
      │
      ▼
Ollama (LLM)
      │
      ▼
Grounded Answer
```

---

# Technologies Used

- Python
- FastAPI
- APScheduler
- Weaviate
- Ollama
- Phi-3 Mini
- Sentence Transformers
- Cross Encoder (ms-marco-MiniLM-L-6-v2)

---

# Project Structure

```
rag_api/
│
├── chat.py
├── chunker.py
├── embeddings.py
├── hybrid_search.py
├── metadata.py
├── pipeline.py
├── prompt.py
├── query_classifier.py
├── reranker.py
├── weaviate_db.py
└── main.py

data/
├── judgments.json
├── metadata/
├── markdown/
└── pdfs/

evaluation.json
evaluation.md
DECISIONS.md
README.md
```

---

# Data Schema

Each judgment record contains:

- serial_number
- case
- remarks
- other_citation
- phc_neutral_citation
- decision_date
- sc_status
- category
- scraped_at
- id
- pdf_path

---

# Duplicate Prevention

Duplicate documents are prevented using:

- Neutral Citation
- Deterministic UUIDs for chunks
- Content hashing

This ensures the ingestion pipeline is idempotent.

---

# Metadata Generation

Metadata is generated using **Ollama (Phi-3 Mini)**.

Each judgment is converted into a metadata JSON file before ingestion.

---

# Retrieval Improvements (Stage 3)

## Hybrid Search

The system combines:

- Dense Vector Search
- BM25 Keyword Search

The results are merged before reranking.

---

## Cross Encoder Reranking

Model:

```
cross-encoder/ms-marco-MiniLM-L-6-v2
```

The reranker reorders retrieved chunks according to semantic relevance.

---

## Query Classification

Queries are classified into:

- Citation
- Case Number
- Summary
- Section
- Act
- Judge
- Date
- Keyword
- Semantic

This enables future routing and rejection of off-domain queries.

---

# Evaluation

A manual evaluation dataset containing **20 questions** was created.

Results:

| System | Accuracy |
|---------|----------|
| Vector Search | 65% |
| Hybrid Search + Reranker | 85% |

Hybrid retrieval with reranking improved retrieval accuracy by **20 percentage points**.

---

# Running the Project

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Start Ollama

```bash
ollama serve
```

Run the model:

```bash
ollama run phi3:mini
```

---

## Start Weaviate

```bash
docker compose up -d
```

---

## Start FastAPI

```bash
uvicorn rag_api.main:app --reload
```

---

## Ingest Data

POST request:

```
POST /ingest
```

Body:

```json
{
    "json_path":"data/judgments.json"
}
```

---

## Chat Endpoint

POST request:

```
POST /chat
```

Example:

```json
{
    "question":"Section 145 CPC",
    "top_k":5
}
```

---

# Future Improvements

- Metadata filtering before vector search
- Better citation lookup
- Improved query classification
- Metadata-aware reranking
- Migration to Weaviate Client v4

---

# Author

Nimra Jabran
