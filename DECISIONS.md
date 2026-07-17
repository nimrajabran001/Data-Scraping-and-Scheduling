# DECISIONS.md

# 1. Data Schema (judgments.json)

Each record in the dataset follows the JSON structure below:

- serial_number (string) — Case serial number
- case (string) — Case title or name
- remarks (string) — Additional notes or remarks
- other_citation (string) — Alternative citation reference
- phc_neutral_citation (string) — Primary unique citation identifier
- decision_date (string) — Date of judgment/decision
- sc_status (string) — Supreme Court status indicator
- category (string) — Case category or classification
- scraped_at (string) — Timestamp of scraping
- id (string) — Unique internal identifier
- pdf_path (string) — Local or stored path of the PDF file

---

# 2. Idempotency (Duplicate Prevention)

Duplicate records are prevented using:

- Primary uniqueness key: **phc_neutral_citation**
- Deterministic UUIDs for document chunks in Weaviate.
- Content hashing to detect unchanged records.

This ensures each judgment is indexed only once even if the scraper runs multiple times.

---

# 3. Scheduling

Automated scraping is handled using:

- APScheduler for periodic execution of scraping tasks.

This enables continuous data collection without manual intervention.

---

# 4. Site Etiquette & Responsible Scraping

To ensure ethical scraping:

- `robots.txt` is respected.
- `time.sleep(1)` delay between requests.
- Low request rate.
- No aggressive parallel requests.

---

# 5. Data Storage Strategy

- Scraped judgments are stored as structured JSON.
- PDFs are downloaded locally.
- Markdown is generated from PDFs.
- Metadata JSON files are generated for every judgment.
- Chunks and embeddings are stored in Weaviate.

---

# 6. Metadata Generation

Metadata is generated using **Ollama (Phi-3 Mini)**.

For each judgment the following fields are extracted:

- Case Title
- Case Number
- Court
- Bench
- Judge
- Decision Date
- Neutral Citation
- Other Citation
- Category
- Summary
- Keywords
- Legal Issues
- Acts
- Sections
- Final Decision

The metadata is stored as JSON and indexed into Weaviate to improve retrieval quality.

---

# 7. Hybrid Search

Originally the system relied only on dense vector search.

Stage 3 introduced Hybrid Search consisting of:

- Dense Vector Search
- BM25 Keyword Search
- Result Merging

This improves retrieval for:

- Citation lookup
- Section lookup
- Legal terminology
- Case numbers
- Broad legal concepts

---

# 8. Cross-Encoder Reranking

A Cross Encoder reranker was added after retrieval.

Model used:

`cross-encoder/ms-marco-MiniLM-L-6-v2`

Pipeline:

1. Retrieve top candidates using Hybrid Search.
2. Score every query-document pair.
3. Sort by Cross Encoder score.
4. Return the highest-ranked documents.

This significantly improved retrieval accuracy.

---

# 9. Query Classification

A lightweight rule-based classifier was implemented.

Supported query categories:

- Citation lookup
- Case number
- Summary request
- Section lookup
- Act lookup
- Judge lookup
- Date lookup
- Keyword search
- Semantic search

Off-domain queries (for example weather, cooking, cricket, Bitcoin, etc.) are identified separately and can be rejected or routed differently in future improvements.

---

# 10. Evaluation

A manual evaluation dataset containing **20 questions** was created.

Questions include:

- Citation lookup
- Case lookup
- Section lookup
- Semantic questions
- Summary requests
- Broad legal queries
- Off-domain questions

Results:

| System | Accuracy |
|---------|----------|
| Vector Search | **65%** |
| Hybrid Search + Cross Encoder Reranker | **85%** |

Hybrid retrieval combined with reranking improved retrieval quality by approximately **20 percentage points**.

---

# 11. What Worked

- Metadata generation using Phi-3 Mini.
- Hybrid Search (Vector + BM25).
- Cross Encoder reranking.
- Metadata indexing.
- Incremental ingestion.
- Duplicate prevention.
- Evaluation framework.

---

# 12. Limitations

Some citation-only queries still retrieve incorrect judgments because citation metadata is not searched before vector retrieval.

Judge/date queries are also less accurate because those metadata fields receive little weight during retrieval.

Although off-domain queries are classified, retrieval is still performed instead of rejecting them. Future work would integrate the query classifier directly into the retrieval pipeline to prevent unnecessary searches.