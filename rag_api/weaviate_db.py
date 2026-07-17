import hashlib
import weaviate

from rag_api.config import (
    WEAVIATE_URL,
    CLASS_NAME
)

from rag_api.embeddings import get_embedding


def search(query: str, limit: int = 5):
    """
    Vector search in Weaviate.

    Kept for backward compatibility with any existing callers. New code
    should use rag_api.semantic_search.semantic_search instead, which
    supports court/year/judge filters and returns a normalized `score`.
    """

    vector = get_embedding(query)

    result = (
        client.query
        .get(
            CLASS_NAME,
            [
                "case",
                "text",
                "citation",
                "citation_normalized",
                "decision_date",
                "pdf_url",
                "source_url",
                "serial_number",
                "summary",
                "keywords",
                "legal_issues",
                "final_decision",
                "judge",
                "court",
            ]
        )
        .with_near_vector(
            {
                "vector": vector
            }
        )
        .with_limit(limit)
        .do()
    )

    return result["data"]["Get"][CLASS_NAME]


client = weaviate.Client(WEAVIATE_URL)


def init_schema():
    """
    Create Weaviate schema if it does not already exist.

    Stage 4 additions vs. the original schema:
      - judge: enables judge-reference queries and judge filters
        (Section 2 "judge reference", Section 3.2 metadata attachment)
      - court: enables court filter for multi-court deployments
        (Section 5.1 tool contract `court` param)
      - citation_normalized: canonical "<year> <ABBR> <number>" form so
        "2026 PHC 153" and "2026PHC153" both match in BM25 search
        (Section 3.1 requirement)

    NOTE: if CLASS_NAME already exists from before this migration, adding
    properties to `properties` below does nothing automatically — Weaviate
    does not retroactively alter an existing class. Either:
      (a) drop and recreate the class (loses existing vectors, requires
          full re-ingestion), or
      (b) add the new properties to the existing class via
          client.schema.property.create(CLASS_NAME, {...}) for each new
          field, then re-run /ingest so existing documents get values
          for the new fields.
    Option (b) is safer for an existing corpus; see the migration snippet
    at the bottom of this file.
    """

    existing = client.schema.get()

    classes = [
        c["class"]
        for c in existing.get("classes", [])
    ]

    if CLASS_NAME in classes:
        print("✓ Schema already exists")
        _ensure_new_properties()
        return

    schema = {
        "class": CLASS_NAME,
        "description": "Peshawar High Court Judgments",
        "vectorizer": "none",
        "properties": [

            {
                "name": "text",
                "dataType": ["text"]
            },
            {
                "name": "case",
                "dataType": ["text"]
            },
            {
                "name": "category",
                "dataType": ["text"]
            },
            {
                "name": "remarks",
                "dataType": ["text"]
            },
            {
                "name": "decision_date",
                "dataType": ["text"]
            },
            {
                "name": "citation",
                "dataType": ["text"]
            },
            {
                "name": "citation_normalized",
                "dataType": ["text"]
            },
            {
                "name": "source_url",
                "dataType": ["text"]
            },
            {
                "name": "pdf_url",
                "dataType": ["text"]
            },
            {
                "name": "document_id",
                "dataType": ["text"]
            },
            {
                "name": "chunk_index",
                "dataType": ["int"]
            },
            {
                "name": "serial_number",
                "dataType": ["text"]
            },
            {
                "name": "content_hash",
                "dataType": ["text"]
            },
            {
                "name": "summary",
                "dataType": ["text"]
            },
            {
                "name": "keywords",
                "dataType": ["text"]
            },
            {
                "name": "legal_issues",
                "dataType": ["text"]
            },
            {
                "name": "final_decision",
                "dataType": ["text"]
            },
            {
                "name": "judge",
                "dataType": ["text"]
            },
            {
                "name": "court",
                "dataType": ["text"]
            }

        ]
    }

    client.schema.create_class(schema)

    print("✓ Schema created")


def _ensure_new_properties():
    """
    For an already-existing class from before this migration: add the
    Stage 4 properties (judge, court, citation_normalized) if missing,
    without touching existing data. Safe to call repeatedly.
    """

    existing_class = client.schema.get(CLASS_NAME)
    existing_props = {p["name"] for p in existing_class.get("properties", [])}

    new_props = [
        {"name": "judge", "dataType": ["text"]},
        {"name": "court", "dataType": ["text"]},
        {"name": "citation_normalized", "dataType": ["text"]},
    ]

    for prop in new_props:
        if prop["name"] not in existing_props:
            client.schema.property.create(CLASS_NAME, prop)
            print(f"✓ Added missing property: {prop['name']}")


def make_uuid(document_id: str, chunk_index: int):
    """
    Generate deterministic UUID for each chunk.
    """

    value = f"{document_id}_{chunk_index}"

    return hashlib.md5(
        value.encode()
    ).hexdigest()


def chunk_exists(document_id: str, chunk_index: int) -> bool:
    """
    Check whether a specific chunk already exists.
    """

    uuid = make_uuid(document_id, chunk_index)

    try:

        result = client.data_object.get_by_id(
            uuid,
            class_name=CLASS_NAME
        )

        return result is not None

    except Exception:
        return False


def document_exists(document_id: str) -> bool:
    """
    A document is considered ingested if chunk 0 exists.
    """

    return chunk_exists(document_id, 0)


def batch_insert(records):
    """
    Insert chunks into Weaviate.

    Duplicate checking is performed in pipeline.py,
    but we also guard here for safety.
    """

    inserted = 0

    with client.batch as batch:

        batch.batch_size = 50

        for record in records:

            uuid = make_uuid(
                record["document_id"],
                record["chunk_index"]
            )

            # Skip duplicate chunks
            if chunk_exists(
                    record["document_id"],
                    record["chunk_index"]
            ):
                continue

            vector = record.pop("vector")

            # Ensure Stage 3 metadata fields exist
            record.setdefault("summary", "")
            record.setdefault("keywords", "")
            record.setdefault("legal_issues", "")
            record.setdefault("final_decision", "")
            record.setdefault("category", "")
            record.setdefault("remarks", "")
            record.setdefault("citation", "")
            record.setdefault("decision_date", "")
            record.setdefault("source_url", "")
            record.setdefault("pdf_url", "")
            record.setdefault("serial_number", "")

            # Stage 4 fields
            record.setdefault("judge", "")
            record.setdefault("court", "")
            record.setdefault("citation_normalized", "")

            batch.add_data_object(
                data_object=record,
                class_name=CLASS_NAME,
                uuid=uuid,
                vector=vector
            )

            inserted += 1

    return inserted