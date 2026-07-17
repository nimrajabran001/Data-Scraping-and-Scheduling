from dotenv import load_dotenv
load_dotenv()
import os
from apscheduler.schedulers.blocking import BlockingScheduler
import logging

from Scraper import run_scraper
from storage import JSON_FILE
from rag_api.pipeline import run_ingestion

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# Create APScheduler instance
scheduler = BlockingScheduler()


def job():
    """
    Full nightly pipeline: scrape new judgments (stages 1-2), then run
    ingestion (stages 3-7: MD conversion, metadata, storage upload,
    MongoDB, vector indexing).

    NOTE: previously this job only called run_scraper(), so no scheduled
    run ever exercised stages 3-7 -- ingestion had to be triggered
    manually via POST /ingest. run_ingestion() is stage-aware (see
    rag_api/state_manager.py) so it automatically resumes any record
    left in a failed/incomplete state by a prior run instead of
    reprocessing everything from scratch.
    """

    try:
        logging.info("Scraper started")
        run_scraper()
        logging.info("Scraper finished successfully")
    except Exception as e:
        logging.error(f"Scraper failed: {str(e)}")
        return  # don't attempt ingestion against a run that never scraped

    try:
        logging.info("Ingestion started")
        summary = run_ingestion(JSON_FILE)
        logging.info(f"Ingestion finished: {summary}")
    except Exception as e:
        logging.error(f"Ingestion failed: {str(e)}")


# Schedule job using CRON expression
# This runs the scraper + ingestion daily at 2:00 AM
scheduler.add_job(job, "cron", hour=2, minute=0)

print("Scheduler started...")
scheduler.start()