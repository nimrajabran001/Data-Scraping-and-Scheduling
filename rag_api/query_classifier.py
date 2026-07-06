import re


def classify_query(query):

    q = query.lower().strip()

    if re.search(r"\d{4}\s*phc\s*\d+", q):
        return "citation"

    if re.search(r"(rfa|cra|wp|cr\.a|cr\.p)\s*no", q):
        return "case_number"

    if "vs" in q:
        return "case_name"

    if "summary" in q:
        return "summary"

    if "judge" in q:
        return "judge"

    if "section" in q:
        return "section"

    if "act" in q:
        return "act"

    if "date" in q:
        return "date"

    if len(q.split()) <= 2:
        return "keyword"

    return "semantic"