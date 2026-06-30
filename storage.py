import json
import os

# Path of JSON file where scraped data is stored
JSON_FILE = "data/json/judgments.json"

#Load existing scraped data from JSON file, If file does not exist, return empty list
def load_data():
    os.makedirs("data/json", exist_ok=True)

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

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4, ensure_ascii=False)