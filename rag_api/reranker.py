from sentence_transformers import CrossEncoder

# Load once when the application starts
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def rerank(query: str, results: list, top_k: int = 5):
    """
    Rerank hybrid search results using a CrossEncoder.
    """

    if not results:
        return []

    pairs = [
        (query, item["text"])
        for item in results
    ]

    scores = model.predict(pairs)

    for item, score in zip(results, scores):
        item["rerank_score"] = float(score)

    results.sort(
        key=lambda x: x["rerank_score"],
        reverse=True
    )

    return results[:top_k]