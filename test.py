from dotenv import load_dotenv
load_dotenv()
import json
import statistics
import time

from rag_api.weaviate_db import search as vector_search
from rag_api.hybrid_search import hybrid_search, keyword_search
from rag_api.query_classifier import classify_query

with open("evaluation.json", "r", encoding="utf-8") as f:
    dataset = json.load(f)

RELEVANT_ITEMS = [item for item in dataset if item["category"] != "irrelevant"]
IRRELEVANT_ITEMS = [item for item in dataset if item["category"] == "irrelevant"]

STRATEGIES = {
    "keyword": keyword_search,
    "semantic": vector_search,
    "hybrid": hybrid_search,
}


def _rank_of_correct(results: list, expected_case: str) -> int:
    """1-indexed rank of the first result whose case matches expected_case
    (substring match, same convention the original test.py used)."""

    expected = (expected_case or "").lower()

    if not expected:
        return 0

    for i, r in enumerate(results, start=1):
        if expected in (r.get("case", "") or "").lower():
            return i

    return 0


def evaluate_strategy(name: str, search_fn) -> dict:
    p1_hits, p5_hits, reciprocal_ranks, latencies = [], [], [], []
    by_category = {}

    print(f"\n{'=' * 60}\n{name.upper()}\n{'=' * 60}")

    for item in RELEVANT_ITEMS:

        start = time.perf_counter()
        results = search_fn(item["question"], 5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

        rank = _rank_of_correct(results, item["expected_case"])

        p1 = 1 if rank == 1 else 0
        p5 = 1 if (1 <= rank <= 5) else 0
        rr = (1.0 / rank) if rank else 0.0

        p1_hits.append(p1)
        p5_hits.append(p5)
        reciprocal_ranks.append(rr)

        cat = item["category"]
        by_category.setdefault(cat, {"p1": [], "p5": [], "rr": []})
        by_category[cat]["p1"].append(p1)
        by_category[cat]["p5"].append(p5)
        by_category[cat]["rr"].append(rr)

        predicted = results[0]["case"] if results else ""
        print(f"[{'✓' if p1 else '✗'}] {item['question']!r:55} rank={rank or 'not found'}")
        if not p1:
            print(f"      expected: {item['expected_case'][:70]}")
            print(f"      got     : {predicted[:70]}")

    def _avg(values):
        return round(statistics.mean(values), 4) if values else 0.0

    category_breakdown = {
        cat: {
            "precision_at_1": _avg(v["p1"]),
            "precision_at_5": _avg(v["p5"]),
            "mrr": _avg(v["rr"]),
            "n": len(v["p1"]),
        }
        for cat, v in by_category.items()
    }

    return {
        "strategy": name,
        "precision_at_1": _avg(p1_hits),
        "precision_at_5": _avg(p5_hits),
        "mrr": _avg(reciprocal_ranks),
        "avg_latency_ms": _avg(latencies),
        "n_queries": len(RELEVANT_ITEMS),
        "by_category": category_breakdown,
    }


def evaluate_classifier() -> dict:
    """
    Section 4/8: does the classifier actually reject off-domain queries,
    and does it wrongly reject legitimate legal queries?

    NOTE: per DECISIONS.md Limitation #12, the classifier is currently
    NOT wired into the retrieval path — /chat still runs retrieval even
    on off-domain queries. This function tests the classifier function
    itself in isolation so you have real numbers to decide whether it's
    good enough to gate retrieval on.
    """

    print(f"\n{'=' * 60}\nCLASSIFIER\n{'=' * 60}")

    correctly_rejected = 0
    false_negatives = []  # irrelevant queries wrongly classified as relevant

    for item in IRRELEVANT_ITEMS:
        result = classify_query(item["question"])
        # Adjust this condition to match whatever classify_query returns
        # in your implementation (e.g. a string "irrelevant" or a dict).
        is_irrelevant = (
            result == "irrelevant"
            or (isinstance(result, dict) and result.get("query_type") == "irrelevant")
        )

        print(f"[{'✓' if is_irrelevant else '✗'}] {item['question']!r:45} -> {result}")

        if is_irrelevant:
            correctly_rejected += 1
        else:
            false_negatives.append({"query": item["question"], "classified_as": result})

    false_positives = []  # relevant queries wrongly classified as irrelevant

    for item in RELEVANT_ITEMS:
        result = classify_query(item["question"])
        is_irrelevant = (
            result == "irrelevant"
            or (isinstance(result, dict) and result.get("query_type") == "irrelevant")
        )

        if is_irrelevant:
            false_positives.append({"query": item["question"], "classified_as": result})

    rejection_rate = correctly_rejected / len(IRRELEVANT_ITEMS) if IRRELEVANT_ITEMS else 0.0
    false_positive_rate = len(false_positives) / len(RELEVANT_ITEMS) if RELEVANT_ITEMS else 0.0

    return {
        "n_irrelevant": len(IRRELEVANT_ITEMS),
        "n_relevant": len(RELEVANT_ITEMS),
        "rejection_rate": round(rejection_rate, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "false_negatives": false_negatives,
        "false_positives": false_positives,
    }


def main():
    strategy_results = {
        name: evaluate_strategy(name, fn) for name, fn in STRATEGIES.items()
    }

    classifier_results = evaluate_classifier()

    output = {
        "strategy_results": strategy_results,
        "classifier_results": classifier_results,
    }

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
    print(f"{'Strategy':<10} {'P@1':<8} {'P@5':<8} {'MRR':<8} {'Latency(ms)':<12}")
    for name, r in strategy_results.items():
        print(f"{name:<10} {r['precision_at_1']:<8} {r['precision_at_5']:<8} "
              f"{r['mrr']:<8} {r['avg_latency_ms']:<12}")

    print(f"\nClassifier rejection rate: {classifier_results['rejection_rate']}")
    print(f"Classifier false positive rate: {classifier_results['false_positive_rate']}")
    print("\nFull results written to results.json")


if __name__ == "__main__":
    main()