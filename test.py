import json

from rag_api.weaviate_db import search
from rag_api.hybrid_search import hybrid_search

with open("evaluation.json", "r", encoding="utf-8") as f:
    dataset = json.load(f)


def evaluate(search_function, name):
    correct = 0

    print("\n========================")
    print(name)
    print("========================")

    for item in dataset:

        results = search_function(item["question"], 5)

        if len(results) == 0:
            predicted = ""
        else:
            predicted = results[0]["case"]

        expected = item["expected_case"]

        ok = expected.lower() in predicted.lower()

        if ok:
            correct += 1

        print(item["question"])
        print("Expected :", expected)
        print("Predicted:", predicted)
        print("✓" if ok else "✗")
        print()

    accuracy = correct / len(dataset)

    print(f"Accuracy = {accuracy:.2%}")

    return accuracy


evaluate(search, "Vector Search")

evaluate(hybrid_search, "Hybrid + Reranker")