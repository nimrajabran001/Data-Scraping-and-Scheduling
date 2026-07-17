"""
MongoDB metadata storage ("ingested into MongoDB" pipeline stage).

Tries a direct pymongo connection first (MONGO_URI env var). If that is
unset, unreachable, or a write raises, falls back to the REST API:

    base URL: https://sb.pakistanlawbot.com/api

so ingestion still succeeds in environments where the app can't reach
MongoDB directly.

NOTE: the exact REST contract (path/verb/body shape) below is a
reasonable default (PUT /judgments/{document_id}) -- confirm it against
the real API spec and adjust `_upsert_via_rest_api` / `_exists_via_rest_api`
if the routes differ.
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "phc_judgments")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "judgments")

FALLBACK_API_BASE_URL = os.getenv(
    "MONGO_FALLBACK_API_BASE_URL", "https://sb.pakistanlawbot.com/api"
)
FALLBACK_API_TIMEOUT = float(os.getenv("MONGO_FALLBACK_API_TIMEOUT", "30"))

_mongo_client = None


def _get_mongo_collection():
    """Lazily create and cache a pymongo collection handle. Returns None on any failure."""
    global _mongo_client

    if not MONGO_URI:
        return None

    if _mongo_client is None:
        try:
            import pymongo

            _mongo_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            _mongo_client.admin.command("ping")
        except Exception as e:
            logger.warning(f"MongoDB direct connection unavailable: {e}")
            _mongo_client = None
            return None

    try:
        return _mongo_client[MONGO_DB_NAME][MONGO_COLLECTION]
    except Exception as e:
        logger.warning(f"MongoDB collection handle failed: {e}")
        return None


def _upsert_via_rest_api(document_id: str, metadata: dict) -> bool:
    url = f"{FALLBACK_API_BASE_URL.rstrip('/')}/judgments/{document_id}"

    try:
        response = requests.put(url, json=metadata, timeout=FALLBACK_API_TIMEOUT)
        response.raise_for_status()
        logger.info(f"✓ Metadata pushed via fallback API: {document_id}")
        return True
    except Exception as e:
        logger.error(f"Fallback API ingestion failed for {document_id}: {e}")
        return False


def _exists_via_rest_api(document_id: str) -> Optional[bool]:
    url = f"{FALLBACK_API_BASE_URL.rstrip('/')}/judgments/{document_id}"

    try:
        response = requests.get(url, timeout=15)

        if response.status_code == 404:
            return False

        response.raise_for_status()
        return True

    except Exception as e:
        logger.warning(f"Fallback API existence check failed: {e}")
        return None


def upsert_judgment_metadata(document_id: str, metadata: dict) -> bool:
    """
    Insert or update one judgment's metadata in MongoDB.

    Tries direct pymongo first; on any failure, falls back to the REST
    API base URL. Returns True on success via either path, False if both
    failed (caller should mark the pipeline stage as failed in that case).
    """

    collection = _get_mongo_collection()

    if collection is not None:
        try:
            collection.update_one(
                {"document_id": document_id},
                {"$set": {**metadata, "document_id": document_id}},
                upsert=True,
            )
            logger.info(f"✓ Metadata upserted directly to MongoDB: {document_id}")
            return True
        except Exception as e:
            logger.warning(
                f"Direct MongoDB write failed for {document_id}, falling back to REST API: {e}"
            )

    return _upsert_via_rest_api(document_id, metadata)


def judgment_exists(document_id: str) -> Optional[bool]:
    """
    Returns None if neither the direct connection nor the fallback API
    could answer -- callers should treat "unknown" as "re-run the stage"
    since upsert is idempotent either way.
    """

    collection = _get_mongo_collection()

    if collection is not None:
        try:
            return collection.find_one({"document_id": document_id}) is not None
        except Exception as e:
            logger.warning(f"MongoDB existence check failed: {e}")

    return _exists_via_rest_api(document_id)
