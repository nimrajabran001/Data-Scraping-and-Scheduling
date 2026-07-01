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
                "decision_date",
                "pdf_url",
                "source_url",
                "serial_number"
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
    """

    existing = client.schema.get()

    classes = [
        c["class"]
        for c in existing.get("classes", [])
    ]

    if CLASS_NAME in classes:
        print("✓ Schema already exists")
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
            }

        ]
    }

    client.schema.create_class(schema)

    print("✓ Schema created")


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

            # Extra safety against duplicate inserts
            if chunk_exists(
                record["document_id"],
                record["chunk_index"]
            ):
                continue

            vector = record.pop("vector")

            batch.add_data_object(
                data_object=record,
                class_name=CLASS_NAME,
                uuid=uuid,
                vector=vector
            )

            inserted += 1

    return inserted