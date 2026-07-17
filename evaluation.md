# Evaluation Report

## Evaluation Dataset

A manually created evaluation set containing 20 queries was used.

The dataset contains:

- Citation lookup
- Case number lookup
- Legal concepts
- Summary questions
- Section-based queries
- Semantic questions
- Broad keyword queries
- Off-domain questions

---

# Experiment 1 – Baseline (Vector Search)

Retrieval:
- Dense Vector Search
- No BM25
- No Reranker

Correct Predictions: 13/20

Accuracy:

65%

### Common Failures

- Citation searches failed.
- Case number lookup sometimes retrieved unrelated judgments.
- Generic legal terms such as "execution proceedings" retrieved semantically similar but incorrect cases.
- Broad queries like "Summarize the murder judgment" often returned the wrong criminal case.

---

# Experiment 2 – Hybrid Search + Cross Encoder Reranker

Retrieval:

- Dense Vector Search
- BM25 Keyword Search
- Cross Encoder Reranking

Correct Predictions:

17/20

Accuracy:

85%

### Improvements

Hybrid search significantly improved:

- Section lookup
- Case number retrieval
- Generic legal concepts
- Execution proceedings
- Broad semantic queries

The Cross Encoder reordered retrieved chunks so that the most relevant judgment appeared first.

---

# Accuracy Comparison

| System | Accuracy |
|---------|----------|
| Vector Search | 65% |
| Hybrid + Reranker | 85% |

Improvement:

20 percentage points

---

# Remaining Errors

The system still struggles with:

- Citation-only queries
- Judge/date lookup
- Queries where metadata fields are incomplete
- Off-domain questions are still retrieved because query rejection has not yet been integrated into retrieval.

---

# Conclusion

Adding BM25 retrieval together with Cross Encoder reranking improved retrieval quality considerably.

The overall retrieval accuracy increased from **65%** to **85%**, mainly because keyword search complements semantic search while reranking places the most relevant judgment at the top of the retrieved results.