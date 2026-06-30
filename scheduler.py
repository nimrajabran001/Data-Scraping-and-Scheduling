from apscheduler.schedulers.blocking import BlockingScheduler
from Scraper import run_scraper
import logging

logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# Create APScheduler instance
scheduler = BlockingScheduler()

def job():
    try:
        logging.info("Scraper started")
        run_scraper()
        logging.info("Scraper finished successfully")
    except Exception as e:
        logging.error(f"Scraper failed: {str(e)}")

# Schedule job using CRON expression
# This runs the scraper daily at 2:00 AM
scheduler.add_job(job, "cron", hour=2, minute=0)

print("Scheduler started...")
scheduler.start()