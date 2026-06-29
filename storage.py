import json
import os

JSON_FILE = "data/json/judgments.json"


def load_data():
    os.makedirs("data/json", exist_ok=True)

    if not os.path.exists(JSON_FILE):
        return []

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(records):
    seen = set()
    cleaned = []

    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        cleaned.append(r)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4, ensure_ascii=False)