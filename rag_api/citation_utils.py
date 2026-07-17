"""
Citation normalization utilities.

Pakistani legal citations appear in inconsistent formats:
    "2026 PHC 153"  vs  "2026PHC153"  vs  "2026 P H C 153"

Weaviate's BM25 tokenizer splits on whitespace/punctuation, so
"2026PHC153" and "2026 PHC 153" are NOT treated as equivalent unless
we normalize both the indexed field and the incoming query the same way.

Strategy: at index time (pipeline.py) and at query time (query_classifier.py /
keyword_search), run the citation-bearing text through `normalize_citation`
before it's stored / searched. We store BOTH the raw citation and a
normalized version (`citation_normalized`) so exact-format lookups still work
while fuzzy variants also match.
"""

import re

# Known Pakistani court/report abbreviations we want to recognize.
KNOWN_ABBREVIATIONS = [
    "PHC",   # Peshawar High Court
    "SHC",   # Sindh High Court
    "PLD",   # Pakistan Legal Decisions
    "SCMR",  # Supreme Court Monthly Review
    "CLC",   # Civil Law Cases
    "YLR",   # Yearly Law Reports
    "MLD",   # Monthly Law Digest
]

_CITATION_RE = re.compile(
    r"(\d{4})\s*[-]?\s*("
    + "|".join(KNOWN_ABBREVIATIONS)
    + r")\s*[-]?\s*(\d+)",
    re.IGNORECASE,
)


def normalize_citation(text: str) -> str:
    """
    Find citation-like substrings in `text` and rewrite them into a single
    canonical spaced form: "<year> <ABBR> <number>".

    Example:
        "2026PHC153"      -> "2026 PHC 153"
        "2026 - PHC - 153"-> "2026 PHC 153"
        "See 2026 phc 153 for details" -> "See 2026 PHC 153 for details"

    Non-citation text is returned unchanged.
    """

    if not text:
        return text

    def _replace(match: re.Match) -> str:
        year, abbr, number = match.groups()
        return f"{year} {abbr.upper()} {number}"

    return _CITATION_RE.sub(_replace, text)


def extract_citation(text: str) -> str | None:
    """
    Extract the first normalized citation found in `text`, or None.
    Used by the query classifier to detect citation-lookup queries and
    by the pipeline to populate `citation_normalized` at index time.
    """

    if not text:
        return None

    match = _CITATION_RE.search(text)

    if not match:
        return None

    year, abbr, number = match.groups()

    return f"{year} {abbr.upper()} {number}"


def citations_match(a: str, b: str) -> bool:
    """
    Compare two citation strings ignoring spacing/case/hyphenation.
    """

    norm_a = extract_citation(a) or (a or "").strip().upper()
    norm_b = extract_citation(b) or (b or "").strip().upper()

    return norm_a == norm_b


if __name__ == "__main__":
    # Quick manual sanity checks
    tests = [
        "2026 PHC 153",
        "2026PHC153",
        "2026 - phc - 153",
        "Please see 2026 SHC 87 for the ruling",
        "No citation here",
    ]

    for t in tests:
        print(f"{t!r:45} -> {normalize_citation(t)!r:30} extracted: {extract_citation(t)!r}")
