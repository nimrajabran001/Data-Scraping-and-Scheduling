"""
The search_judgments tool — the single entry point an LLM (or the /chat
and /hybrid HTTP endpoints) calls to retrieve judgments.

Tool contract (Section 5.1):

    search_judgments(
        query: str,
        strategy: str = 'hybrid',   # 'keyword' | 'semantic' | 'hybrid'
        top_k: int = 5,
        court: str = None,
        year: int = None,
        judge: str = None,
    ) -> dict

Returns either:
    {"status": "ok", "results": [JudgmentResult, ...]}
    {"status": "not_applicable", "reason": "...", "message": "..."}
    {"status": "no_results", "message": "..."}

JudgmentResult shape (Section 5.1):
    {case_number, case_title, citation, judge, decision_date, snippet,
     score, source_url}
"""

from typing import Optional

from rag_api.query_classifier import classify_relevance
from rag_api.semantic_search import semantic_search
from rag_api.hybrid_search import hybrid_search, keyword_search
from rag_api.search_config import DEFAULT_TOP_K


REFUSAL_MESSAGE = (
    "I can help you find Pakistani court judgments. Your question doesn't "
    "seem related to that — could you rephrase or ask about a specific "
    "case, judge, or legal issue?"
)


def _make_similarity_fn():
    """
    Build an embedding_similarity_fn for classify_relevance() by running a
    single semantic_search top-1 lookup. Kept as a closure so
    query_classifier.py has zero direct dependency on Weaviate.
    """

    def _similarity(query: str) -> float:
        results = semantic_search(query, limit=1)

        if not results:
            return 0.0

        return results[0].get("score", 0.0)

    return _similarity


def _to_judgment_result(item: dict) -> dict:
    """Map internal Weaviate fields to the public JudgmentResult shape."""

    return {
        "case_number": item.get("case_number", "") or item.get("serial_number", ""),
        "case_title": item.get("case", ""),
        "citation": item.get("citation", ""),
        "judge": item.get("judge", ""),
        "decision_date": item.get("decision_date", ""),
        "snippet": (item.get("text", "") or "")[:400],
        "score": item.get("fusion_score", item.get("score", 0.0)),
        "source_url": item.get("source_url", "") or item.get("pdf_url", ""),
    }


def search_judgments(
    query: str,
    strategy: str = "hybrid",
    top_k: int = DEFAULT_TOP_K,
    court: Optional[str] = None,
    year: Optional[int] = None,
    judge: Optional[str] = None,
) -> dict:
    """
    Main tool implementation. See module docstring for the contract.
    """

    if not query or not query.strip():
        return {
            "status": "not_applicable",
            "reason": "empty_query",
            "message": REFUSAL_MESSAGE,
        }

    # ------------------------------------------------------------
    # Relevance gate (Section 5.2): refuse before hitting the index
    # ------------------------------------------------------------
    relevance = classify_relevance(query, embedding_similarity_fn=_make_similarity_fn())

    if relevance == "irrelevant":
        return {
            "status": "not_applicable",
            "reason": "off_domain",
            "message": REFUSAL_MESSAGE,
        }

    # ------------------------------------------------------------
    # Strategy dispatch
    # ------------------------------------------------------------
    if strategy == "keyword":
        raw_results = keyword_search(query, limit=top_k, court=court, year=year, judge=judge)
    elif strategy == "semantic":
        raw_results = semantic_search(query, limit=top_k, court=court, year=year, judge=judge)
    else:
        raw_results = hybrid_search(query, limit=top_k, court=court, year=year, judge=judge)

    if not raw_results:
        return {
            "status": "no_results",
            "message": (
                "I couldn't find any judgments matching that. Could you "
                "share a citation, case number, or rephrase the legal "
                "issue?"
            ),
        }

    results = [_to_judgment_result(item) for item in raw_results]

    response = {"status": "ok", "results": results}

    if relevance == "ambiguous":
        response["hedge"] = (
            "I found some possible matches, but I'm not fully confident "
            "they're what you're looking for — please double-check the "
            "case details below."
        )

    return response


# ---------------------------------------------------------------------
# Tool schema for LLM tool-calling (Ollama / OpenAI-compatible format)
# ---------------------------------------------------------------------
SEARCH_JUDGMENTS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_judgments",
        "description": (
            "Search Peshawar High Court judgments by citation, case number, "
            "judge, party names, statute/section, or natural-language legal "
            "question. Do NOT call this for greetings, small talk, or "
            "questions unrelated to Pakistani law."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's question, in their own words.",
                },
                "strategy": {
                    "type": "string",
                    "enum": ["keyword", "semantic", "hybrid"],
                    "description": "Retrieval strategy. Default 'hybrid' unless the user asks to compare strategies.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return. Default 5.",
                },
                "court": {
                    "type": "string",
                    "description": "Optional court filter, e.g. 'Peshawar High Court'.",
                },
                "year": {
                    "type": "integer",
                    "description": "Optional decision year filter.",
                },
                "judge": {
                    "type": "string",
                    "description": "Optional judge name filter.",
                },
            },
            "required": ["query"],
        },
    },
}
