from dotenv import load_dotenv
load_dotenv()
import os
import hashlib
from datetime import datetime
import time

# updated from Nimra branch for PR

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager

from storage import load_data, save_data
from downloader import download_pdf

from rag_api.state_manager import (
    Stage,
    StageStatus,
    mark_stage,
    get_document_state,
)

# Robots.txt checked manually before scraping
URL = "https://www.peshawarhighcourt.gov.pk/PHCCMS/reportedJudgments.php?action=search"


def make_id(record):
    raw = f"{record['case'].strip()}_{record['decision_date'].strip()}_{record['phc_neutral_citation'].strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _recover_failed_downloads(existing_data):
    """
    Stage 2 recovery.

    A record can exist in judgments.json with stage 1 (scraped) done but
    stage 2 (pdf_downloaded) failed or pending -- e.g. the site returned
    the row but the PDF request timed out, or the process was killed
    mid-run. The original scraper skipped any id already in
    existing_ids, so those records would never get another download
    attempt. This pass finds them and retries, using the pdf_url now
    stored on the record at scrape time.
    """

    recovered = 0

    for record in existing_data:

        document_id = record.get("id")

        if not document_id:
            continue

        state = get_document_state(document_id)
        pdf_stage_status = state["stages"][Stage.PDF_DOWNLOADED.value]["status"]

        # Already have a real file on disk -> just backfill the state
        # record (covers records ingested before state tracking existed).
        if record.get("pdf_path") and os.path.exists(record["pdf_path"]):
            if pdf_stage_status != StageStatus.SUCCESS.value:
                mark_stage(document_id, Stage.PDF_DOWNLOADED, StageStatus.SUCCESS)
            continue

        if pdf_stage_status == StageStatus.SUCCESS.value:
            continue

        pdf_url = record.get("pdf_url")

        if not pdf_url:
            # Nothing to retry with; leave it failed for manual inspection.
            mark_stage(
                document_id, Stage.PDF_DOWNLOADED, StageStatus.FAILED,
                "No pdf_url stored on record; cannot retry download."
            )
            continue

        try:
            filename = f"{document_id}.pdf"
            local_path = download_pdf(pdf_url, "data/pdfs", filename)

            record["pdf_path"] = local_path
            mark_stage(document_id, Stage.PDF_DOWNLOADED, StageStatus.SUCCESS)
            recovered += 1

        except Exception as e:
            record["pdf_path"] = None
            mark_stage(document_id, Stage.PDF_DOWNLOADED, StageStatus.FAILED, str(e))

    if recovered:
        print(f"↻ Recovered {recovered} previously-failed PDF download(s)")

    return existing_data


def run_scraper():

    os.makedirs("data/json", exist_ok=True)
    os.makedirs("data/pdfs", exist_ok=True)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    wait = WebDriverWait(driver, 15)

    try:
        driver.get(URL)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr")))

        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")

        existing_data = load_data()

        # ---------------------------------------------------
        # Recover any records left in a failed/incomplete state 2 from
        # a previous run before we look for brand-new rows.
        # ---------------------------------------------------
        existing_data = _recover_failed_downloads(existing_data)

        existing_ids = {item["id"] for item in existing_data}

        new_records = []

        for row in rows:
            # respectful delay to avoid server overload
            time.sleep(1)
            cols = row.find_elements(By.TAG_NAME, "td")

            if len(cols) < 8:
                continue

            record = {
                "serial_number": cols[0].text,
                "case": cols[1].text,
                "remarks": cols[2].text,
                "other_citation": cols[3].text,
                "phc_neutral_citation": cols[4].text,
                "decision_date": cols[5].text,
                "sc_status": cols[6].text,
                "category": cols[7].text,
                "scraped_at": datetime.utcnow().isoformat()
            }

            record_id = make_id(record)
            record["id"] = record_id

            if record_id in existing_ids:
                continue

            # ---------------------------------------------------
            # Stage 1: data extracted from the site -- this record's
            # fields above came straight out of the table row, so
            # extraction itself has already succeeded at this point.
            # ---------------------------------------------------
            mark_stage(record_id, Stage.SCRAPED, StageStatus.SUCCESS)

            try:
                pdf_element = row.find_element(
                    By.XPATH,
                    ".//a[contains(@href,'pdf')]"
                )
                pdf_url = pdf_element.get_attribute("href")
                record["pdf_url"] = pdf_url

                filename = f"{record_id}.pdf"
                local_path = download_pdf(pdf_url, "data/pdfs", filename)

                record["pdf_path"] = local_path

                # ---------------------------------------------------
                # Stage 2: PDF downloaded
                # ---------------------------------------------------
                mark_stage(record_id, Stage.PDF_DOWNLOADED, StageStatus.SUCCESS)

            except Exception as e:
                record["pdf_path"] = None
                mark_stage(record_id, Stage.PDF_DOWNLOADED, StageStatus.FAILED, str(e))

            new_records.append(record)

        updated_data = existing_data + new_records
        save_data(updated_data)

        print(f"New records: {len(new_records)} | Total: {len(updated_data)}")

    finally:
        driver.quit()


if __name__ == "__main__":
    run_scraper()