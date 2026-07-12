import json
import logging
import os

from tqdm import tqdm


from rag_api.chunker import smart_chunk
from rag_api.drive import upload_to_drive
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
    Process one judgment record.
    """

    document_id = record.get("id")

    if not document_id:
        logger.warning("Missing document id")
        return 0

    # ---------------------------------------------------
    # Incremental ingestion
    # ---------------------------------------------------

    current_hash = calculate_record_hash(record)

    saved_hash = record.get("content_hash")

    metadata_path = record.get("metadata_path")

    if (
            document_exists(document_id)
            and saved_hash == current_hash
            and metadata_path
            and os.path.exists(metadata_path)
    ):
        logger.info(
            f"Skipping unchanged document: {document_id}"
        )
        return 0

    record["content_hash"] = current_hash

    pdf_path = record.get("pdf_path")

    if not pdf_path:
        logger.warning("Missing pdf_path")
        return 0

    pdf_path = os.path.normpath(pdf_path)

    if not os.path.exists(pdf_path):
        logger.warning(f"PDF not found: {pdf_path}")
        return 0

    try:

        # ---------------------------------------------------
        # Markdown
        # ---------------------------------------------------

        md_path = record.get("markdown_path")

        if md_path and os.path.exists(md_path):

            markdown_text = read_markdown(md_path)

            logger.info("Using existing markdown")

        else:

            markdown_text, md_path = pdf_to_markdown(pdf_path)

            record["markdown_path"] = (
                md_path.replace("\\", "/")
            )

            logger.info(
                f"Markdown created: {md_path}"
            )

        # ---------------------------------------------------
        # Metadata
        #
        # FIX (Stage 4): the original code had `return 1` inside this
        # else-branch, which exited process_record() before Drive
        # upload / chunking / embedding / insertion ever ran on a
        # document's FIRST ingestion pass — those steps only happened on
        # a second run, once metadata_path already existed. Removed the
        # early return so a single /ingest call fully processes new
        # documents.
        # ---------------------------------------------------

        metadata_path = record.get("metadata_path")
        metadata = {}

        if metadata_path and os.path.exists(metadata_path):

            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            logger.info("Using existing metadata")

        else:

            metadata = generate_metadata(
                record,
                markdown_text
            )

            metadata_path = save_metadata(
                metadata
            )

            record["metadata_path"] = (
                metadata_path.replace("\\", "/")
            )

            logger.info(
                f"Metadata created: {metadata_path}"
            )

        # ---------------------------------------------------
        # Google Drive
        # ---------------------------------------------------

        drive_url = record.get("google_drive_url")

        if drive_url:

            logger.info("Using existing Google Drive URL")

        else:

            drive_url = upload_to_drive(pdf_path)

            record["google_drive_url"] = drive_url

            logger.info("Uploaded PDF to Google Drive")

        record["pdf_path"] = os.path.normpath(
            record["pdf_path"]
        ).replace("\\", "/")

        record["markdown_path"] = os.path.normpath(
            record["markdown_path"]
        ).replace("\\", "/")

        # ---------------------------------------------------
        # Chunking
        # ---------------------------------------------------

        chunks = smart_chunk(markdown_text)

        if not chunks:
            logger.warning("No chunks generated")
            return 0

        # ---------------------------------------------------
        # Stage 4 derived fields
        # ---------------------------------------------------

        raw_citation = record.get("phc_neutral_citation", "")
        citation_normalized = normalize_citation(raw_citation) if raw_citation else ""

        judge = metadata.get("judge", "") or metadata.get("bench", "")
        court = record.get("court", DEFAULT_COURT)

        # ---------------------------------------------------
        # Build Weaviate objects
        # ---------------------------------------------------

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

                "decision_date": record.get(
                    "decision_date",
                    ""
                ),

                "citation": raw_citation,

                "citation_normalized": citation_normalized,

                "source_url": record.get(
                    "source_url",
                    ""
                ),

                "pdf_url": drive_url,

                "serial_number": record.get(
                    "serial_number",
                    ""
                ),

                "summary": metadata.get(
                    "summary",
                    ""
                ),

                "keywords": ", ".join(
                    metadata.get(
                        "keywords",
                        []
                    )
                ),

                "legal_issues": ", ".join(
                    metadata.get(
                        "legal_issues",
                        []
                    )
                ),

                "final_decision": metadata.get(
                    "final_decision",
                    ""
                ),

                "judge": judge,

                "court": court,

                "document_id": document_id,

                "chunk_index": chunk_index,

                "vector": vector

            })

        if not objects:
            return 0

        inserted = batch_insert(objects)

        logger.info(
            f"{record.get('case')} -> {inserted} chunks inserted"
        )

        return inserted

    except Exception as e:

        logger.exception(e)

        return 0


def run_ingestion(json_path: str):

    if not os.path.exists(json_path):
        raise FileNotFoundError(json_path)

    with open(
        json_path,
        "r",
        encoding="utf-8"
    ) as f:

        records = json.load(f)

    total_documents = 0
    total_chunks = 0

    logger.info(
        f"Processing {len(records)} judgments"
    )

    for record in tqdm(records):

        inserted = process_record(record)

        if inserted:

            total_documents += 1
            total_chunks += inserted

    # ---------------------------------------------------
    # Save updated metadata
    # ---------------------------------------------------

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            records,
            f,
            indent=4,
            ensure_ascii=False
        )

    logger.info("JSON metadata updated.")

    return {

        "documents_processed": total_documents,

        "chunks_inserted": total_chunks

    }