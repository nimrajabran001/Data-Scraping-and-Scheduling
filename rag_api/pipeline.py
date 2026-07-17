import json
import logging
import os

from tqdm import tqdm

from rag_api.chunker import smart_chunk
from rag_api.s3_storage import upload_to_s3
from rag_api.embeddings import get_embedding
from rag_api.pdf_utils import (
    pdf_to_markdown,
    read_markdown
)
from rag_api.metadata import (
    generate_metadata,
    save_metadata
)

from rag_api.weaviate_db import (
    batch_insert,
    document_exists
)

from rag_api.hash_utils import calculate_record_hash
from rag_api.citation_utils import normalize_citation
from rag_api.mongo_db import upsert_judgment_metadata
from rag_api.state_manager import (
    Stage,
    StageStatus,
    mark_stage,
    get_resume_stage,
    get_document_state,
    stage_index,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

# Default court label for this corpus. If you ever ingest a second court
# into the same index, set this per-record instead (e.g. from a "court"
# key already present in your Stage 1 JSON).
DEFAULT_COURT = "Peshawar High Court"


def process_record(record: dict):
    """
    Process one judgment record through the 7 pipeline stages:

        1. scraped
        2. pdf_downloaded
        3. md_converted
        4. metadata_prepared
        5. uploaded_storage   (S3 / Drive)
        6. mongo_ingested
        7. vector_indexed

    On repeat runs, resumes from the first stage that did not succeed
    last time instead of redoing everything or silently skipping the
    document. Each stage is wrapped individually so a failure at any
    point is recorded precisely and does not require re-running earlier,
    already-successful stages.
    """

    document_id = record.get("id")

    if not document_id:
        logger.warning("Missing document id")
        return 0

    # The scraper already wrote this record to JSON before process_record()
    # was ever called on it, so stage 1 is done by definition.
    mark_stage(document_id, Stage.SCRAPED, StageStatus.SUCCESS)

    resume_stage = get_resume_stage(document_id)
    resume_idx = stage_index(resume_stage)

    logger.info(f"[{document_id}] resuming from stage: {resume_stage.value}")

    # ---------------------------------------------------
    # Fast path: fully processed on a previous run and content unchanged
    # ---------------------------------------------------
    current_hash = calculate_record_hash(record)
    saved_hash = record.get("content_hash")

    if (
        resume_idx >= stage_index(Stage.VECTOR_INDEXED)
        and document_exists(document_id)
        and saved_hash == current_hash
    ):
        logger.info(f"[{document_id}] fully processed already, skipping")
        return 0

    record["content_hash"] = current_hash

    pdf_path = record.get("pdf_path")
    markdown_text = None
    md_path = record.get("markdown_path")
    metadata = {}

    try:
        # ---------------------------------------------------
        # Stage 2: PDF downloaded
        # (Actual download happens in the scraper; here we verify the
        # file really is on disk before anything downstream depends on it.)
        # ---------------------------------------------------
        if resume_idx <= stage_index(Stage.PDF_DOWNLOADED):
            if not pdf_path:
                mark_stage(document_id, Stage.PDF_DOWNLOADED, StageStatus.FAILED, "Missing pdf_path")
                logger.warning(f"[{document_id}] Missing pdf_path")
                return 0

            pdf_path = os.path.normpath(pdf_path)

            if not os.path.exists(pdf_path):
                mark_stage(document_id, Stage.PDF_DOWNLOADED, StageStatus.FAILED, f"PDF not found: {pdf_path}")
                logger.warning(f"[{document_id}] PDF not found: {pdf_path}")
                return 0

            mark_stage(document_id, Stage.PDF_DOWNLOADED, StageStatus.SUCCESS)
        else:
            # resume_idx says this stage already succeeded, but guard
            # against a corrupted/stale record where pdf_path is
            # missing anyway (e.g. hand-edited JSON, partial writes) --
            # otherwise os.path.normpath(None) raises a raw TypeError
            # that aborts the whole ingestion run instead of just this
            # one document.
            if not pdf_path:
                mark_stage(
                    document_id, Stage.PDF_DOWNLOADED, StageStatus.FAILED,
                    "pdf_path missing despite stage marked success previously"
                )
                logger.warning(f"[{document_id}] pdf_path is None; re-marked stage as failed for retry")
                return 0

            pdf_path = os.path.normpath(pdf_path)

        # ---------------------------------------------------
        # Stage 3: MD converted
        # ---------------------------------------------------
        if resume_idx <= stage_index(Stage.MD_CONVERTED):
            try:
                if md_path and os.path.exists(md_path):
                    markdown_text = read_markdown(md_path)
                    logger.info(f"[{document_id}] Using existing markdown")
                else:
                    markdown_text, md_path = pdf_to_markdown(pdf_path)
                    record["markdown_path"] = md_path.replace("\\", "/")
                    logger.info(f"[{document_id}] Markdown created: {md_path}")

                mark_stage(document_id, Stage.MD_CONVERTED, StageStatus.SUCCESS)

            except Exception as e:
                mark_stage(document_id, Stage.MD_CONVERTED, StageStatus.FAILED, str(e))
                logger.exception(e)
                return 0
        else:
            if not md_path or not os.path.exists(md_path):
                mark_stage(
                    document_id, Stage.MD_CONVERTED, StageStatus.FAILED,
                    "markdown_path missing or file not found despite stage marked success previously"
                )
                logger.warning(f"[{document_id}] markdown_path invalid; re-marked stage as failed for retry")
                return 0

            markdown_text = read_markdown(md_path)

        # ---------------------------------------------------
        # Stage 4: Metadata prepared
        # ---------------------------------------------------
        metadata_path = record.get("metadata_path")

        if resume_idx <= stage_index(Stage.METADATA_PREPARED):
            try:
                if metadata_path and os.path.exists(metadata_path):
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    logger.info(f"[{document_id}] Using existing metadata")
                else:
                    metadata = generate_metadata(record, markdown_text)
                    metadata_path = save_metadata(metadata)
                    record["metadata_path"] = metadata_path.replace("\\", "/")
                    logger.info(f"[{document_id}] Metadata created: {metadata_path}")

                mark_stage(document_id, Stage.METADATA_PREPARED, StageStatus.SUCCESS)

            except Exception as e:
                mark_stage(document_id, Stage.METADATA_PREPARED, StageStatus.FAILED, str(e))
                logger.exception(e)
                return 0
        else:
            if not metadata_path or not os.path.exists(metadata_path):
                mark_stage(
                    document_id, Stage.METADATA_PREPARED, StageStatus.FAILED,
                    "metadata_path missing or file not found despite stage marked success previously"
                )
                logger.warning(f"[{document_id}] metadata_path invalid; re-marked stage as failed for retry")
                return 0

            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

        # ---------------------------------------------------
        # Stage 5: Uploaded to S3
        # (record.get("google_drive_url") is checked as a fallback so
        # documents uploaded before this S3 migration don't get
        # re-uploaded -- remove that fallback once you've backfilled
        # old records into S3, if you want everything on one storage.)
        # ---------------------------------------------------
        storage_url = record.get("s3_url") or record.get("google_drive_url")

        if resume_idx <= stage_index(Stage.UPLOADED_STORAGE):
            try:
                if storage_url:
                    logger.info(f"[{document_id}] Using existing storage URL")
                else:
                    storage_url = upload_to_s3(pdf_path)
                    record["s3_url"] = storage_url
                    logger.info(f"[{document_id}] Uploaded PDF to S3")

                mark_stage(document_id, Stage.UPLOADED_STORAGE, StageStatus.SUCCESS)

            except Exception as e:
                mark_stage(document_id, Stage.UPLOADED_STORAGE, StageStatus.FAILED, str(e))
                logger.exception(e)
                return 0

        record["pdf_path"] = os.path.normpath(pdf_path).replace("\\", "/")
        record["markdown_path"] = os.path.normpath(md_path).replace("\\", "/")

        raw_citation = record.get("phc_neutral_citation", "")
        citation_normalized = normalize_citation(raw_citation) if raw_citation else ""
        judge = metadata.get("judge", "") or metadata.get("bench", "")
        court = record.get("court", DEFAULT_COURT)

        # ---------------------------------------------------
        # Stage 6: Ingested into MongoDB
        # (Falls back to https://sb.pakistanlawbot.com/api if a direct
        # MongoDB connection is unavailable -- see rag_api/mongo_db.py)
        # ---------------------------------------------------
        if resume_idx <= stage_index(Stage.MONGO_INGESTED):
            try:
                mongo_doc = {
                    **metadata,
                    "citation": raw_citation,
                    "citation_normalized": citation_normalized,
                    "judge": judge,
                    "court": court,
                    "pdf_url": storage_url,
                    "source_url": record.get("source_url", ""),
                }

                ok = upsert_judgment_metadata(document_id, mongo_doc)

                if not ok:
                    raise RuntimeError("Both direct MongoDB and fallback API ingestion failed")

                mark_stage(document_id, Stage.MONGO_INGESTED, StageStatus.SUCCESS)

            except Exception as e:
                # Non-fatal: Mongo is a secondary metadata store, not what
                # search actually depends on (Weaviate is). Mark the stage
                # failed so it's retried on the next run per the normal
                # resume logic, but don't block vector indexing on it --
                # a Mongo outage shouldn't stop the search index from
                # being populated.
                mark_stage(document_id, Stage.MONGO_INGESTED, StageStatus.FAILED, str(e))
                logger.warning(f"[{document_id}] MongoDB ingestion failed, continuing to vector indexing: {e}")

        # ---------------------------------------------------
        # Stage 7: Added to vector DB
        # ---------------------------------------------------
        vector_stage_status = get_document_state(document_id)["stages"][Stage.VECTOR_INDEXED.value]["status"]

        if vector_stage_status == StageStatus.SUCCESS.value:
            logger.info(f"[{document_id}] vector indexing already succeeded, skipping re-embed")
            return 0

        if resume_idx <= stage_index(Stage.VECTOR_INDEXED):
            try:
                chunks = smart_chunk(markdown_text)

                if not chunks:
                    mark_stage(document_id, Stage.VECTOR_INDEXED, StageStatus.FAILED, "No chunks generated")
                    logger.warning(f"[{document_id}] No chunks generated")
                    return 0

                objects = []

                for chunk_index, chunk in enumerate(chunks):
                    vector = get_embedding(chunk)

                    if vector is None:
                        continue

                    objects.append({
                        "text": chunk,
                        "case": record.get("case", ""),
                        "remarks": record.get("remarks", ""),
                        "category": record.get("category", ""),
                        "decision_date": record.get("decision_date", ""),
                        "citation": raw_citation,
                        "citation_normalized": citation_normalized,
                        "source_url": record.get("source_url", ""),
                        "pdf_url": storage_url,
                        "serial_number": record.get("serial_number", ""),
                        "summary": metadata.get("summary", ""),
                        "keywords": ", ".join(metadata.get("keywords", [])),
                        "legal_issues": ", ".join(metadata.get("legal_issues", [])),
                        "final_decision": metadata.get("final_decision", ""),
                        "judge": judge,
                        "court": court,
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "vector": vector,
                    })

                if not objects:
                    mark_stage(document_id, Stage.VECTOR_INDEXED, StageStatus.FAILED, "No embeddable chunks")
                    logger.warning(f"[{document_id}] No embeddable chunks")
                    return 0

                inserted = batch_insert(objects)

                mark_stage(document_id, Stage.VECTOR_INDEXED, StageStatus.SUCCESS)

                logger.info(f"{record.get('case')} -> {inserted} chunks inserted")

                return inserted

            except Exception as e:
                mark_stage(document_id, Stage.VECTOR_INDEXED, StageStatus.FAILED, str(e))
                logger.exception(e)
                return 0

        # Already fully vector-indexed on a previous run and nothing else changed
        return 0

    except Exception as e:
        logger.exception(e)
        return 0


def run_ingestion(json_path: str):

    if not os.path.exists(json_path):
        raise FileNotFoundError(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    total_documents = 0
    total_chunks = 0

    logger.info(f"Processing {len(records)} judgments")

    for record in tqdm(records):

        inserted = process_record(record)

        if inserted:
            total_documents += 1
            total_chunks += inserted

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

    logger.info("JSON metadata updated.")

    return {
        "documents_processed": total_documents,
        "chunks_inserted": total_chunks,
    }