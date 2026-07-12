"""
Keyword (BM25) and Hybrid (fused) search.

Section 3.1 requirement: "2026 PHC 153" and "2026PHC153" must match the same
document. We handle this by normalizing the query before we send it to
Weaviate's BM25, AND by normalizing the indexed `citation` field at ingest
time into a second field `citation_normalized` (see pipeline.py patch note
in DECISIONS.md). We search both `citation` and `citation_normalized`.

Section 3.3 requirement: fusion must be a documented, configurable method.
We implement Reciprocal Rank Fusion (RRF) as the default because:
  - it needs no score normalization (BM25 and cosine scores are on
    incomparable scales, so a naive weighted sum is fragile without
    careful calibration)
  - it's a single well-understood constant (k) to tune
  - it's robust to one ranker returning wildly different score ranges
    than the other
A weighted-sum alternative is also implemented and selectable via
search_config.FUSION_METHOD for the head-to-head comparison in Section 7.
"""

import time
from typing import List, Optional

from rag_api.weaviate_db import client
from rag_api.config import CLASS_NAME
from rag_api.reranker import rerank
from rag_api.citation_utils import normalize_citation
from rag_api.semantic_search import semantic_search, _build_where_filter
from rag_api.search_config import (
    FUSION_METHOD,
    RRF_K,
    VECTOR_WEIGHT,
    BM25_WEIGHT,
    RERANK_AFTER_FUSION,
    CANDIDATE_POOL_SIZE,
)

RETURN_FIELDS = [
    "case",
    "text",
    "summary",
    "keywords",
    "legal_issues",
    "final_decision",
    "citation",
    "citation_normalized",
    "decision_date",
    "pdf_url",
    "source_url",
    "judge",
    "court",
]


def keyword_search(
    query: str,
    limit: int = 20,
    court: Optional[str] = None,
    year: Optional[int] = None,
    judge: Optional[str] = None,
) -> List[dict]:
    """
    BM25 keyword search over case/citation/text/keywords/legal_issues.

    The query is normalized so "2026PHC153" and "2026 PHC 153" produce the
    same BM25 tokens as whatever is stored in `citation_normalized`.
    """

    normalized_query = normalize_citation(query)

    q = (
        client.query
        .get(CLASS_NAME, RETURN_FIELDS)
        .with_bm25(
            query=normalized_query,
            properties=[
                "case",
                "citation",
                "citation_normalized",
                "text",
                "keywords",
                "legal_issues",
                "judge^2",   # boost exact judge-name matches
            ],
        )
        .with_limit(limit)
        .with_additional(["score"])
    )

    where_filter = _build_where_filter(court=court, year=year, judge=judge)

    if where_filter:
        q = q.with_where(where_filter)

    result = q.do()

    items = result.get("data", {}).get("Get", {}).get(CLASS_NAME, []) or []

    for item in items:
        additional = item.pop("_additional", {}) or {}
        try:
            item["score"] = float(additional.get("score", 0.0))
        except (TypeError, ValueError):
            item["score"] = 0.0

    return items


def keyword_search_timed(query: str, **kwargs) -> tuple[List[dict], float]:
    start = time.perf_counter()
    results = keyword_search(query, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return results, elapsed_ms


def _item_key(item: dict) -> tuple:
    """Stable identity for a chunk, used for dedup and rank lookups."""
    return (item.get("case"), item.get("text"))


def _reciprocal_rank_fusion(
    vector_results: List[dict],
    keyword_results: List[dict],
    k: int = RRF_K,
) -> List[dict]:
    """
    RRF score for each item = sum over rankers of 1 / (k + rank).
    Item present in only one ranker still gets a score from that ranker.
    """

    scores: dict = {}
    items_by_key: dict = {}

    for rank, item in enumerate(vector_results, start=1):
        key = _item_key(item)
        items_by_key[key] = item
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)

    for rank, item in enumerate(keyword_results, start=1):
        key = _item_key(item)
        items_by_key.setdefault(key, item)
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)

    fused = []

    for key, score in scores.items():
        item = dict(items_by_key[key])
        item["fusion_score"] = score
        fused.append(item)

    fused.sort(key=lambda x: x["fusion_score"], reverse=True)

    return fused


def _normalize_scores(items: List[dict], score_key: str) -> dict:
    """Min-max normalize a score field across a result list -> {key: norm_score}."""

    if not items:
        return {}

    values = [item.get(score_key, 0.0) or 0.0 for item in items]
    lo, hi = min(values), max(values)

    normalized = {}

    for item in items:
        raw = item.get(score_key, 0.0) or 0.0
        norm = 0.0 if hi == lo else (raw - lo) / (hi - lo)
        normalized[_item_key(item)] = norm

    return normalized


def _weighted_sum_fusion(
    vector_results: List[dict],
    keyword_results: List[dict],
    vector_weight: float = VECTOR_WEIGHT,
    bm25_weight: float = BM25_WEIGHT,
) -> List[dict]:
    """
    Normalize each ranker's scores to [0,1], then combine with fixed weights.
    Simpler to explain than RRF but sensitive to score-distribution shape
    (e.g. a BM25 run with one dominant hit skews normalization).
    """

    vector_norm = _normalize_scores(vector_results, "score")
    keyword_norm = _normalize_scores(keyword_results, "score")

    items_by_key = {}

    for item in vector_results + keyword_results:
        items_by_key.setdefault(_item_key(item), item)

    fused = []

    for key, item in items_by_key.items():
        v = vector_norm.get(key, 0.0)
        b = keyword_norm.get(key, 0.0)
        combined = vector_weight * v + bm25_weight * b

        merged = dict(item)
        merged["fusion_score"] = combined
        fused.append(merged)

    fused.sort(key=lambda x: x["fusion_score"], reverse=True)

    return fused


def hybrid_search(
    query: str,
    limit: int = 5,
    court: Optional[str] = None,
    year: Optional[int] = None,
    judge: Optional[str] = None,
    fusion_method: Optional[str] = None,
) -> List[dict]:
    """
    Fuse vector search + BM25 keyword search into one ranking.

    fusion_method overrides search_config.FUSION_METHOD for one-off calls
    (used by the eval harness to sweep "rrf" vs "weighted").
    """

    method = fusion_method or FUSION_METHOD

    vector_results = semantic_search(
        query, limit=CANDIDATE_POOL_SIZE, court=court, year=year, judge=judge
    )
    keyword_results = keyword_search(
        query, limit=CANDIDATE_POOL_SIZE, court=court, year=year, judge=judge
    )

    if method == "weighted":
        fused = _weighted_sum_fusion(vector_results, keyword_results)
    else:
        fused = _reciprocal_rank_fusion(vector_results, keyword_results)

    if RERANK_AFTER_FUSION:
        fused = rerank(query, fused, top_k=CANDIDATE_POOL_SIZE)

    # Keep only one chunk per case, preserving fused order
    unique = []
    used_cases = set()

    for item in fused:
        case = item.get("case")

        if case in used_cases:
            continue

        unique.append(item)
        used_cases.add(case)

        if len(unique) == limit:
            break

    return unique


def hybrid_search_timed(query: str, **kwargs) -> tuple[List[dict], float]:
    start = time.perf_counter()
    results = hybrid_search(query, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return results, elapsed_ms
