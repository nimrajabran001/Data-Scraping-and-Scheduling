"""
Pipeline state management.

Tracks each judgment's progress through 7 pipeline stages so an
interrupted or partially-failed ingestion run can resume from the last
successful stage on the next run, instead of restarting from scratch or
silently skipping the document.

Stages (in required order):
    1. scraped            - record extracted from the court website
    2. pdf_downloaded      - judgment PDF confirmed present on disk
    3. md_converted        - PDF converted to Markdown
    4. metadata_prepared   - LLM-derived metadata JSON generated
    5. uploaded_storage    - PDF uploaded to remote storage (S3 / Drive)
    6. mongo_ingested      - metadata pushed to MongoDB
    7. vector_indexed      - chunks embedded + inserted into Weaviate

State is persisted to a local JSON file (STATE_FILE) keyed by
document_id, so recovery works even if MongoDB/S3/Weaviate happen to be
unreachable when a new run starts.
"""

import json
import os
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

STATE_FILE = os.getenv("PIPELINE_STATE_FILE", "data/state/pipeline_state.json")

# Guards concurrent read-modify-write of the state file within one process.
# (Ingestion is currently single-process/sequential; this just makes the
# module safe if that ever changes.)
_lock = threading.Lock()


class Stage(str, Enum):
    SCRAPED = "scraped"
    PDF_DOWNLOADED = "pdf_downloaded"
    MD_CONVERTED = "md_converted"
    METADATA_PREPARED = "metadata_prepared"
    UPLOADED_STORAGE = "uploaded_storage"
    MONGO_INGESTED = "mongo_ingested"
    VECTOR_INDEXED = "vector_indexed"


STAGE_ORDER = [
    Stage.SCRAPED,
    Stage.PDF_DOWNLOADED,
    Stage.MD_CONVERTED,
    Stage.METADATA_PREPARED,
    Stage.UPLOADED_STORAGE,
    Stage.MONGO_INGESTED,
    Stage.VECTOR_INDEXED,
]


class StageStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank_document_state() -> dict:
    return {
        "stages": {
            stage.value: {"status": StageStatus.PENDING.value, "timestamp": None, "error": None}
            for stage in STAGE_ORDER
        },
        "last_updated": None,
    }


def _load_all() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt/empty state file should never crash a run -- treat as empty.
        return {}


def _save_all(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, STATE_FILE)  # atomic on POSIX


def get_document_state(document_id: str) -> dict:
    with _lock:
        state = _load_all()
    return state.get(document_id, _blank_document_state())


def mark_stage(document_id: str, stage: Stage, status: StageStatus, error: Optional[str] = None) -> None:
    """Record the outcome of one stage for one document."""
    with _lock:
        state = _load_all()
        doc_state = state.get(document_id, _blank_document_state())
        doc_state["stages"][stage.value] = {
            "status": status.value,
            "timestamp": _now(),
            "error": error,
        }
        doc_state["last_updated"] = _now()
        state[document_id] = doc_state
        _save_all(state)


def get_resume_stage(document_id: str) -> Stage:
    """
    Return the first stage that is NOT marked success for this document.

    A brand-new document resumes from SCRAPED. A document where every
    stage up through MONGO_INGESTED succeeded but VECTOR_INDEXED failed
    (or never ran) resumes from VECTOR_INDEXED only -- earlier stages are
    not repeated.
    """
    doc_state = get_document_state(document_id)

    for stage in STAGE_ORDER:
        if doc_state["stages"][stage.value]["status"] != StageStatus.SUCCESS.value:
            return stage

    return STAGE_ORDER[-1]  # every stage already succeeded


def is_fully_ingested(document_id: str) -> bool:
    doc_state = get_document_state(document_id)
    return all(
        doc_state["stages"][stage.value]["status"] == StageStatus.SUCCESS.value
        for stage in STAGE_ORDER
    )


def stage_index(stage: Stage) -> int:
    return STAGE_ORDER.index(stage)


def get_failed_documents() -> dict:
    """
    Convenience for a monitoring/CLI command: which documents have at
    least one failed stage right now, and which stage failed.
    """
    with _lock:
        state = _load_all()

    failed = {}

    for document_id, doc_state in state.items():
        for stage in STAGE_ORDER:
            entry = doc_state["stages"][stage.value]
            if entry["status"] == StageStatus.FAILED.value:
                failed[document_id] = {"stage": stage.value, "error": entry["error"]}
                break

    return failed
