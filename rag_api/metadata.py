import json
import logging
import os
import re

import ollama

logger = logging.getLogger(__name__)

MODEL = "phi3:mini"


def clean_json_response(text: str) -> str:
    """
    Remove markdown code blocks and extract JSON.
    """

    text = text.strip()

    # Remove ```json ... ```
    text = re.sub(r"^```json", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    # Extract first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match:
        return match.group(0)

    return text


def generate_metadata(record: dict, markdown_text: str):
    """
    Generate metadata using Ollama.
    """

    prompt = f"""
You are an expert legal metadata extraction assistant.

Read the following judgment carefully.

Extract ONLY the information present in the judgment.

Return ONLY a valid JSON object.

Do NOT include markdown.

Do NOT include explanations.

If a field is missing, return an empty string "" or an empty list [].

Return this exact schema:

{{
    "case_title":"",
    "case_number":"",
    "court":"",
    "bench":"",
    "judge":"",
    "decision_date":"",
    "neutral_citation":"",
    "other_citation":"",
    "category":"",
    "summary":"",
    "keywords":[],
    "legal_issues":[],
    "acts":[],
    "sections":[],
    "final_decision":""
}}

Judgment:

{markdown_text[:3500]}
"""

    try:

        response = ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        text = response["message"]["content"]

        text = clean_json_response(text)

        metadata = json.loads(text)

    except Exception as e:

        logger.error(f"Metadata generation failed: {e}")

        metadata = {
            "case_title": "",
            "case_number": "",
            "court": "",
            "bench": "",
            "judge": "",
            "decision_date": "",
            "neutral_citation": "",
            "other_citation": "",
            "category": "",
            "summary": "",
            "keywords": [],
            "legal_issues": [],
            "acts": [],
            "sections": [],
            "final_decision": ""
        }

    # -----------------------------------------------------
    # Add existing scraper information
    # -----------------------------------------------------

    metadata["document_id"] = record.get("id", "")

    metadata["case"] = record.get("case", "")

    metadata["remarks"] = record.get("remarks", "")

    metadata["decision_date"] = record.get(
        "decision_date",
        metadata.get("decision_date", "")
    )

    metadata["category"] = record.get(
        "category",
        metadata.get("category", "")
    )

    metadata["neutral_citation"] = record.get(
        "phc_neutral_citation",
        metadata.get("neutral_citation", "")
    )

    metadata["pdf_path"] = record.get("pdf_path", "")

    metadata["markdown_path"] = record.get("markdown_path", "")

    return metadata


def save_metadata(metadata: dict):
    """
    Save metadata JSON.
    """

    folder = "data/metadata"

    os.makedirs(folder, exist_ok=True)

    filename = metadata["document_id"] + ".json"

    path = os.path.join(folder, filename)

    with open(path, "w", encoding="utf-8") as f:

        json.dump(
            metadata,
            f,
            indent=4,
            ensure_ascii=False
        )

    logger.info(f"Metadata saved: {path}")

    return path