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

# Robots.txt checked manually before scraping
URL = "https://www.peshawarhighcourt.gov.pk/PHCCMS/reportedJudgments.php?action=search"


def make_id(record):
    raw = f"{record['case'].strip()}_{record['decision_date'].strip()}_{record['phc_neutral_citation'].strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


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


            try:
                pdf_element = row.find_element(
                    By.XPATH,
                    ".//a[contains(@href,'pdf')]"
                )
                pdf_url = pdf_element.get_attribute("href")

                filename = f"{record_id}.pdf"
                local_path = download_pdf(pdf_url, "data/pdfs", filename)

                record["pdf_path"] = local_path

            except Exception:
                record["pdf_path"] = None

            new_records.append(record)

        updated_data = existing_data + new_records
        save_data(updated_data)

        print(f"New records: {len(new_records)} | Total: {len(updated_data)}")

    finally:
        driver.quit()


if __name__ == "__main__":
    run_scraper()