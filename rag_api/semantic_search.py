"""
Standalone semantic (dense vector) search.

This wraps the near-vector query already used inside hybrid_search.py, but
exposes it as an independently callable, filterable function so it can be
benchmarked on its own in the Section 6 evaluation (Precision@1, Precision@5,
MRR, latency) without going through fusion or reranking.

Filters (court, year, judge) are pushed down into Weaviate's `with_where`
so we don't have to filter in Python after the fact.
"""

import time
from typing import List, Optional

from rag_api.weaviate_db import client
from rag_api.embeddings import get_embedding
from rag_api.config import CLASS_NAME
from rag_api.search_config import CANDIDATE_POOL_SIZE

RETURN_FIELDS = [
    "case",
    "text",
    "summary",
    "keywords",
    "legal_issues",
    "final_decision",
    "citation",
    "decision_date",
    "pdf_url",
    "source_url",
    "judge",
    "court",
]


def _build_where_filter(
    court: Optional[str] = None,
    year: Optional[int] = None,
    judge: Optional[str] = None,
) -> Optional[dict]:
    """
    Build a Weaviate `where` filter from optional structured filters.
    Returns None if no filters are set (so callers can skip .with_where()).
    """

    operands = []

    if court:
        operands.append(
            {
                "path": ["court"],
                "operator": "Equal",
                "valueText": court,
            }
        )

    if year:
        # decision_date is stored as text; match on substring containing
        # the year. If you migrate decision_date to a proper date type,
        # switch this to a range filter on valueDate.
        operands.append(
            {
                "path": ["decision_date"],
                "operator": "Like",
                "valueText": f"*{year}*",
            }
        )

    if judge:
        operands.append(
            {
                "path": ["judge"],
                "operator": "Like",
                "valueText": f"*{judge}*",
            }
        )

    if not operands:
        return None

    if len(operands) == 1:
        return operands[0]

    return {
        "operator": "And",
        "operands": operands,
    }


def semantic_search(
    query: str,
    limit: int = 5,
    court: Optional[str] = None,
    year: Optional[int] = None,
    judge: Optional[str] = None,
) -> List[dict]:
    """
    Pure dense-vector search. No BM25, no fusion, no reranking.

    Returns up to `limit` results, each with a `score` field derived from
    Weaviate's certainty (cosine similarity mapped to [0,1]) so downstream
    code (fusion, eval) has a consistent score field to work with.
    """

    vector = get_embedding(query)

    if vector is None:
        return []

    q = (
        client.query
        .get(CLASS_NAME, RETURN_FIELDS)
        .with_near_vector({"vector": vector})
        .with_limit(max(limit, CANDIDATE_POOL_SIZE))
        .with_additional(["certainty"])
    )

    where_filter = _build_where_filter(court=court, year=year, judge=judge)

    if where_filter:
        q = q.with_where(where_filter)

    result = q.do()

    items = result.get("data", {}).get("Get", {}).get(CLASS_NAME, []) or []

    for item in items:
        additional = item.pop("_additional", {}) or {}
        item["score"] = additional.get("certainty", 0.0)

    return items[:limit]


def semantic_search_timed(query: str, **kwargs) -> tuple[List[dict], float]:
    """
    Same as semantic_search but also returns latency in milliseconds.
    Used by the eval harness so latency is measured consistently across
    strategies.
    """

    start = time.perf_counter()
    results = semantic_search(query, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return results, elapsed_ms
