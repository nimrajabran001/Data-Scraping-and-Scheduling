# Retrieval Strategy Comparison — Peshawar High Court Judgment Search

## Executive Summary

On this 26-item evaluation set (20 relevant + 6 irrelevant), **keyword
(BM25) search actually achieved the highest Precision@1 (0.80) and MRR
(0.84)** of the three strategies, edging out hybrid (P@1 0.70, MRR 0.79)
and comfortably beating semantic-only (P@1 0.45, MRR 0.58). All three tied
on Precision@5 (keyword 0.90, hybrid 0.90, semantic 0.75). Hybrid's real
value wasn't raw top-1 accuracy — it was **rescuing queries that keyword
missed entirely** (e.g. a date-lookup and a heavily paraphrased legal
question), at the cost of being wrong slightly more often on queries
keyword already nailed. This is a genuine, if slightly counter-intuitive,
finding — not what "hybrid should always win" intuition predicts — and is
explained in Negative Results below.

## Per-Strategy Analysis

### Keyword (BM25) — P@1 0.80, P@5 0.90, MRR 0.8375, avg latency 64.2ms
- **How it works**: BM25 over indexed judgment text/metadata.
- **Best for**: exact citations, case numbers, section/act references,
  and — surprisingly — even most paraphrased semantic queries in this set,
  because Pakistani legal paraphrases still share enough vocabulary
  ("surety," "sentence," "guarantor") with the source judgments.
- **Fails on**: `judge` queries (P@1 0.0), `date` queries (P@1 0.0), and
  the one paraphrase specifically engineered to avoid shared vocabulary
  ("can someone who signed as a guarantor... refuse to honor that
  commitment?" — no hit in top 5 at all).
- **Fastest strategy by far**: 64ms avg, ~2.2x faster than hybrid, ~6x
  faster than semantic.

### Semantic (dense vector) — P@1 0.45, P@5 0.75, MRR 0.5833, avg latency 403.7ms*
*includes one-time embedding-model load cost — see latency caveat below.
- **How it works**: sentence-transformer (`all-MiniLM-L6-v2`) nearest-
  neighbor search.
- **Best for**: the one paraphrase keyword completely missed (P@1 1.0 on
  its own `semantic` category, n=6).
- **Fails badly on**: `case_number` (0.0), `section` (0.0), `judge` (0.0),
  `case_name` (0.0) — anything with an exact identifier gets blurred by
  embeddings.
- **Weakest overall strategy on this corpus** — worse than keyword on 8 of
  10 query categories.

### Hybrid (Vector + BM25 + Cross-Encoder rerank) — P@1 0.70, P@5 0.90, MRR 0.7917, avg latency 142.5ms
- **How it works**: merge vector + BM25 candidates, rerank with
  `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- **Best for**: `date` (1.0, keyword got 0.0 here), `case_name` (1.0),
  `semantic` (1.0), `summary` (1.0), `act` (1.0) — ties or wins on 5 of 10
  categories versus keyword.
- **Worse than keyword on**: `citation` (0.0 vs 1.0), `case_number` (0.0
  vs 1.0), `section` (0.0 vs 1.0) — the reranker is actively *hurting*
  exact-identifier lookups that BM25 alone got right, likely because the
  Cross-Encoder wasn't trained on citation-string matching and reorders
  based on semantic similarity of the surrounding text instead.
- **Never worse than semantic on any category.**

## Query-Type Breakdown

| Category    | Keyword P@1 | Semantic P@1 | Hybrid P@1 | Best strategy |
|-------------|-------------|---------------|-------------|----------------|
| citation    | 1.00        | 0.00          | 0.00        | Keyword        |
| case_number | 1.00        | 0.00          | 0.00        | Keyword        |
| case_name   | 1.00        | 0.00          | 1.00        | Keyword / Hybrid |
| judge       | 0.00        | 0.00          | 0.00        | None (all fail)|
| section     | 1.00        | 0.00          | 0.00        | Keyword        |
| act         | 1.00        | 1.00          | 1.00        | Tie            |
| date        | 0.00        | 0.00          | 1.00        | Hybrid         |
| summary     | 1.00        | 0.50          | 1.00        | Keyword / Hybrid |
| semantic    | 0.83        | 0.83          | 1.00        | Hybrid         |
| keyword (misc) | 0.75     | 0.50          | 0.75        | Keyword / Hybrid |

**Takeaway**: keyword wins or ties on 8/10 categories; hybrid wins or ties
on 6/10; semantic never wins outright anywhere except tying `act`. Hybrid's
only clear, unshared win is `date`.

## Cost & Latency Comparison

| Strategy | Indexing cost | Per-query cost | Avg latency (ms) |
|----------|-----------------|------------------|---------------------|
| Keyword  | $0 (BM25, local Weaviate) | $0 | **64.19** |
| Semantic | $0 (local sentence-transformer) | $0 | 403.70* |
| Hybrid   | $0 + reranker inference | $0 | 142.54 |

**\*Latency measurement caveat**: `semantic` was benchmarked first in
`test.py`'s run order, and its 403.7ms average includes the one-time
`Loading embedding model: sentence-transformers/all-MiniLM-L6-v2` cost
visible in the log — the model wasn't warm yet. `hybrid` ran afterward with
the model already loaded, so its 142.5ms is not a fair apples-to-apples
comparison against semantic's cold-start number. **To get a real semantic
latency figure**, either call `get_embedding("warmup")` once before timing
starts, or discard the first N calls of each strategy before averaging.
Re-run and update this table before treating "semantic is 3x slower than
hybrid" as a real finding — it may just be 1.5-2x slower once warm.

## Recommendation

- **Ship one strategy**: **Keyword (BM25)**, based on this data — it has
  the best P@1/MRR, is 2-6x faster than the alternatives, and only loses
  outright on `judge`/`date` lookups and heavily-paraphrased semantic
  queries.
- **Ship two, if allowed**: **Keyword primary + Hybrid fallback**, routed
  by the existing query classifier: use keyword for `citation`,
  `case_number`, `section`, `act`, `case_name` query types (where it's
  perfect), and fall back to hybrid for `date` and open-ended `semantic`
  queries (where it uniquely wins). This avoids hybrid's citation/section
  regressions entirely while still catching the paraphrase keyword misses.

## Negative Results

- **Hybrid did not universally beat keyword** — on this test set it lost
  outright on `citation`, `case_number`, and `section` categories, where
  the Cross-Encoder reranker seems to actively demote the BM25-correct
  result. This contradicts the common assumption that "hybrid + reranker
  is strictly better" and is worth investigating further (e.g. does the
  reranker need citation-aware negative examples, or should exact-match
  categories skip reranking entirely?).
- **Only 1 clean "semantic beats keyword" example existed** in this set,
  not 3+ as initially expected — this corpus's BM25 index already handles
  most paraphrasing because Pakistani legal English reuses a small,
  consistent vocabulary ("surety," "liability," "sentence," "execution").
  Semantic search's real edge only shows up on paraphrases specifically
  engineered to avoid any shared words.
- **`judge` queries failed across all three strategies** (P@1 0.0
  everywhere) — consistent with the known limitation already documented
  in `DECISIONS.md` §12 that judge metadata receives little retrieval
  weight. This wasn't fixed by adding hybrid/reranking; it needs a
  structural fix (e.g. filtering/boosting on a dedicated `judge` field)
  rather than a better ranking algorithm.
- **Classifier has a real false negative**: "What does the First
  Amendment of the US Constitution protect?" was classified `relevant`
  when it should be `irrelevant` (wrong jurisdiction). See Classifier
  Evaluation below.
- **The eval set is skewed**: 14 of 20 relevant queries map to only 2
  underlying judgments (2026 PHC 3823 and 2026 PHC 4078). Numbers here
  may not generalize to the full corpus's actual query diversity — worth
  expanding the eval set further before treating these percentages as
  final.

## Concrete Examples (Section 7.2)

### Keyword wins over semantic (3 examples)
1. `2026 PHC 3823` — keyword rank 1, semantic rank 2. Exact citation;
   embeddings blur the numeric identifier.
2. `RFA No. 263-A of 2023` — keyword rank 1, semantic **not found** in
   top 5. Case number has no semantic content to embed meaningfully.
3. `Section 145 CPC` — keyword rank 1, semantic **not found**. Statute
   references are exact-token matches, not semantic concepts.

### Semantic wins over keyword (only 1 found, not 3 — see Negative Results)
1. `Can someone who signed as a guarantor in a court case later refuse to
   honor that commitment?` — semantic rank 1, keyword **not found**. This
   paraphrase deliberately avoids the judgment's actual terms ("surety,"
   "Section 128"), which is exactly the gap semantic search is designed
   to close. No second or third example met this bar in the current set —
   flagged as a real gap to address by adding more true paraphrases to
   the eval set (see DECISIONS.md open items).

### Hybrid beats both individually (only 1 found, not 3 — see Negative Results)
1. `Decision on 18-06-2026` — keyword rank 2 (miss), semantic rank 3
   (miss), hybrid rank 1 (hit). Neither raw ranker had the right document
   at rank 1, but fusion pulled it to the top. No other query in the set
   showed both underlying rankers failing while hybrid succeeded — most
   of hybrid's other "wins" were really keyword or semantic already
   succeeding and hybrid tying them.

### All three fail (1 example)
1. `Who decided 2026 PHC 4078?` — keyword rank 4, semantic **not found**,
   hybrid **not found**. Hypothesis: the judge's name is likely present
   only as sparse metadata (or briefly in a header/signature block) and
   isn't well-represented in either the BM25 index or the embedding of
   the chunked judgment text — consistent with the `judge`-category P@1
   of 0.0 across all three strategies. This needs a structural fix
   (dedicated judge-field boosting/filtering), not a ranking fix.

## Classifier Evaluation (Section 8)

- **Implementation**: rule-based keyword/regex classifier
  (`rag_api/query_classifier.py`), returning `{"relevance": ..., "query_type": ...}`.
- **Rejection rate**: 0.8333 (5/6 irrelevant queries correctly rejected)
- **False positive rate**: 0.0 (0/20 relevant queries wrongly rejected)
- **Known integration gap**: per `DECISIONS.md` §12, the classifier result
  is computed but not yet used to gate retrieval in `/chat` — it currently
  runs alongside search rather than blocking it. Fixing this is separate
  from the classifier's raw accuracy, which is already good.

### Confusion matrix

|                          | Predicted relevant | Predicted irrelevant |
|--------------------------|----------------------|------------------------|
| Actually relevant (n=20) | 20                   | 0 (false positives)    |
| Actually irrelevant (n=6)| 1 (false negative)  | 5                       |

### False positive example (relevant query wrongly rejected)
None observed in this test set (0/20).

### False negative example (irrelevant query wrongly accepted)
`"What does the First Amendment of the US Constitution protect?"` →
classified `{"relevance": "relevant", "query_type": "relevant"}`.
**Interpretation**: the classifier's rules likely key off legal-sounding
words ("Amendment," "Constitution," "protect") without checking
jurisdiction. This is the exact "legal-sounding but wrong jurisdiction"
trap Section 4.1 calls out — the current rule-based classifier has no
mechanism to distinguish "constitution" (Pakistani, in-corpus) from
"US Constitution" (out-of-corpus). Fix: add an explicit
"other-jurisdiction" keyword list (US Supreme Court, UK law, Indian
Penal Code, etc.) that overrides the generic legal-keyword match.
