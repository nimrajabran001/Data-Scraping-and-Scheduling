import json
import os

# Path of JSON file where scraped data is stored.
# NOTE: standardized to match Readme.md / rag_api/main.py's /ingest example
# ("data/judgments.json"), which previously pointed at a different path
# ("data/json/judgments.json") than this file did -- run_ingestion() was
# silently never seeing what the scraper wrote.
JSON_FILE = "data/judgments.json"

#Load existing scraped data from JSON file, If file does not exist, return empty list
def load_data():
    os.makedirs(os.path.dirname(JSON_FILE) or ".", exist_ok=True)

    if not os.path.exists(JSON_FILE):
        return []

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

#Save records to JSON file, Also removes duplicate entries using "id"
# Ensures idempotency (no repeated data)
def save_data(records):
    seen = set()
    cleaned = []

    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        cleaned.append(r)

    os.makedirs(os.path.dirname(JSON_FILE) or ".", exist_ok=True)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4, ensure_ascii=False)