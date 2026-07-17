"""
Query classification for the search pipeline.

Two separate concerns, kept as two functions so each can be tested and
tuned independently:

1. classify_relevance(query) -> "relevant" | "irrelevant" | "ambiguous"
   Decides whether the query belongs to this corpus at all (Section 4).

2. classify_query_type(query) -> "citation" | "case_number" | "case_name" |
   "judge" | "section" | "act" | "date" | "summary" | "definition" |
   "relevant" | "ambiguous"
   Decides WHICH retrieval strategy/filters to use once we already know
   the query is relevant (Section 2/3 routing).

Section 4.1 definitions used here:
  - Relevant: could plausibly be answered by a Pakistani court judgment —
    case lookups, legal doctrine, procedure, precedent, statute/
    constitutional questions, judge/advocate references.
  - Irrelevant: small talk, non-legal topics (cooking, weather, tech,
    celebrity gossip), or legal questions about systems this corpus does
    not cover (e.g. US case law).
  - Ambiguous: legal-sounding queries with no clear corpus match (e.g. a
    Peshawar corpus asked about a Sindh-specific ruling by name). We route
    ambiguous queries to hybrid search anyway (best effort) but flag them
    so the LLM can hedge ("I found a possible match, but I'm not fully
    confident it's what you're looking for").

Implementation choice (Section 4.2): a two-stage classifier.
  Stage 1 — cheap keyword/regex rules (near-zero cost, catches the obvious
    cases: greetings, off-domain keywords, exact citation patterns).
  Stage 2 — embedding-similarity threshold fallback for anything Stage 1
    doesn't confidently resolve: embed the query, compare against the
    corpus via a real Weaviate nearVector query, take the top-1 certainty.
    Below IRRELEVANCE_SIMILARITY_THRESHOLD -> irrelevant.
    Between the two thresholds -> ambiguous.
    Above AMBIGUOUS_SIMILARITY_THRESHOLD -> relevant.
  We picked this over a zero-shot LLM classifier because it's ~10-50x
  cheaper per query (one embedding call vs. a full LLM completion) and
  deterministic, which matters for reproducing the Section 6 numbers.
  Trade-off: thresholds need tuning (see DECISIONS.md for the sweep) and
  it can be fooled by legal-sounding phrasing about non-Pakistani law.
"""

import re
from typing import Optional

from rag_api.citation_utils import extract_citation
from rag_api.search_config import (
    IRRELEVANCE_SIMILARITY_THRESHOLD,
    AMBIGUOUS_SIMILARITY_THRESHOLD,
)

LEGAL_KEYWORDS = [
    "section", "article", "constitution", "ppc", "crpc", "cpc", "act",
    "judge", "justice", "court", "judgment", "judgement", "case",
    "citation", "appeal", "petition", "criminal", "civil", "murder",
    "contract", "surety", "bail", "conviction", "sentence", "evidence",
    "decree", "execution", "plaintiff", "defendant", "respondent",
    "appellant", "vs", "versus", "writ", "custody", "fundamental rights",
]

OFF_DOMAIN_KEYWORDS = [
    "weather", "temperature", "rain", "cake", "biryani", "recipe",
    "bitcoin", "crypto", "football", "cricket", "movie", "music", "song",
    "instagram", "facebook", "youtube", "python", "java", "c++",
    "javascript", "hotel", "restaurant", "celebrity", "gossip",
]

GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|salaam|assalamualaikum)\b",
    r"^\s*(thanks|thank you|ok|okay|bye|goodbye)\s*[!.]*\s*$",
]

# Legal systems this corpus does NOT cover — treat as irrelevant even
# though the phrasing is legal.
OTHER_JURISDICTION_KEYWORDS = [
    "us supreme court", "u.s. supreme court", "uk supreme court",
    "indian supreme court", "english law", "american law", "eu law",
    "california law", "new york law",
]


def _matches_any(q: str, patterns: list) -> bool:
    return any(re.search(p, q) for p in patterns)


def _contains_any(q: str, words: list) -> bool:
    return any(word in q for word in words)


def classify_relevance(
    query: str,
    embedding_similarity_fn: Optional[callable] = None,
) -> str:
    """
    Returns "relevant", "irrelevant", or "ambiguous".

    embedding_similarity_fn: optional callable(query) -> float in [0,1],
    the top-1 corpus similarity score. Inject this from the caller (e.g.
    a thin wrapper around semantic_search) so this module has no direct
    Weaviate dependency and stays easy to unit test. If not provided,
    Stage 1 keyword rules are used alone (less accurate, but the module
    still works standalone).
    """

    q = query.lower().strip()

    if not q:
        return "irrelevant"

    # Stage 1a: greetings / small talk
    if _matches_any(q, GREETING_PATTERNS):
        return "irrelevant"

    # Stage 1b: explicit off-domain topics
    if _contains_any(q, OFF_DOMAIN_KEYWORDS):
        return "irrelevant"

    # Stage 1c: other jurisdictions not covered by this corpus
    if _contains_any(q, OTHER_JURISDICTION_KEYWORDS):
        return "irrelevant"

    # Stage 1d: exact citation -> definitely relevant, skip embedding call
    if extract_citation(q):
        return "relevant"

    # Stage 1e: obvious legal keyword present -> confidently relevant
    if _contains_any(q, LEGAL_KEYWORDS):
        return "relevant"

    # Stage 2: embedding-similarity fallback for anything ambiguous so far
    if embedding_similarity_fn is not None:
        similarity = embedding_similarity_fn(query)

        if similarity < IRRELEVANCE_SIMILARITY_THRESHOLD:
            return "irrelevant"

        if similarity < AMBIGUOUS_SIMILARITY_THRESHOLD:
            return "ambiguous"

        return "relevant"

    # No embedding fallback available and no keyword signal either way.
    # Default to "ambiguous" rather than silently guessing "relevant" —
    # this is a deliberate, documented choice: false negatives here just
    # cost a hedge in the LLM's phrasing, not a wrong hard rejection.
    return "ambiguous"


def classify_query_type(query: str) -> str:
    """
    Assumes the query has already passed classify_relevance() as
    "relevant" or "ambiguous". Decides which retrieval strategy/filters
    to apply. Logic preserved from the original keyword-routing classifier,
    with citation extraction now delegated to citation_utils.
    """

    q = query.lower().strip()

    if extract_citation(q):
        return "citation"

    if re.search(
        r"(rfa|cra|cr\.a|cr\.p|c\.r|wp|w\.p|crl\.a|cma)\s*no",
        q,
    ):
        return "case_number"

    if q.startswith("what is") or q.startswith("define") or q.startswith("meaning of"):
        return "definition"

    if " vs " in q or " versus " in q:
        return "case_name"

    if "judge" in q or "justice" in q:
        return "judge"

    if "section" in q or "article" in q:
        return "section"

    if " act" in q:
        return "act"

    if "date" in q or "decision date" in q or "decided on" in q:
        return "date"

    if any(w in q for w in ["summary", "summarize", "summarise", "brief", "overview"]):
        return "summary"

    for word in LEGAL_KEYWORDS:
        if word in q:
            return "relevant"

    if len(q.split()) <= 2:
        return "ambiguous"

    return "relevant"


def classify_query(query: str, embedding_similarity_fn: Optional[callable] = None) -> dict:
    """
    Convenience wrapper combining both stages, used by chat.py / the
    search tool. Returns a dict so callers get both pieces of information
    without two separate calls.
    """

    relevance = classify_relevance(query, embedding_similarity_fn=embedding_similarity_fn)

    if relevance == "irrelevant":
        return {"relevance": relevance, "query_type": "irrelevant"}

    return {"relevance": relevance, "query_type": classify_query_type(query)}
