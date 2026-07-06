from rag_api.weaviate_db import client
from rag_api.embeddings import get_embedding
from rag_api.config import CLASS_NAME
from rag_api.reranker import rerank


def vector_search(query: str, limit: int = 20):

    vector = get_embedding(query)

    result = (
        client.query
        .get(
            CLASS_NAME,
            [
                "case",
                "text",
                "summary",
                "keywords",
                "legal_issues",
                "final_decision",
                "citation",
                "decision_date",
                "pdf_url",
                "source_url"
            ]
        )
        .with_near_vector({"vector": vector})
        .with_limit(limit)
        .do()
    )

    return result["data"]["Get"][CLASS_NAME]


def keyword_search(query: str, limit: int = 20):

    result = (
        client.query
        .get(
            CLASS_NAME,
            [
                "case",
                "text",
                "summary",
                "keywords",
                "legal_issues",
                "final_decision",
                "citation",
                "decision_date",
                "pdf_url",
                "source_url"
            ]
        )
        .with_bm25(query=query)
        .with_limit(limit)
        .do()
    )

    return result["data"]["Get"][CLASS_NAME]


def hybrid_search(query: str, limit: int = 5):

    vector_results = vector_search(query, limit=20)
    keyword_results = keyword_search(query, limit=20)

    merged = []
    seen = set()

    for item in vector_results + keyword_results:

        key = (
            item.get("case"),
            item.get("text")
        )

        if key not in seen:
            merged.append(item)
            seen.add(key)

    # Rerank all candidates
    reranked = rerank(
        query,
        merged,
        top_k=20
    )

    # Keep only one chunk per case
    unique = []
    used_cases = set()

    for item in reranked:

        case = item.get("case")

        if case in used_cases:
            continue

        unique.append(item)
        used_cases.add(case)

        if len(unique) == limit:
            break

    return unique