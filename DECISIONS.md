# DECISIONS.md

## 1. Data Schema (judgments.json)

Each record in the dataset follows the JSON structure below:

serial_number (string) — Case serial number
case (string) — Case title or name
remarks (string) — Additional notes or remarks
other_citation (string) — Alternative citation reference
phc_neutral_citation (string) — Primary unique citation identifier
decision_date (string) — Date of judgment/decision
sc_status (string) — Supreme Court status indicator
category (string) — Case category or classification
scraped_at (string) — Timestamp of scraping
id (string) — Unique internal identifier
pdf_path (string) — Local or stored path of the PDF file
## 2. Idempotency (Duplicate Prevention)

Duplicate records are prevented using:

Primary uniqueness key: phc_neutral_citation

This ensures that each judgment is stored only once, even if scraped multiple times.

## 3. Scheduling

Automated scraping is handled using:

APScheduler for periodic and scheduled execution of scraping tasks

This ensures continuous and controlled data collection without manual intervention.

## 4. Site Etiquette & Responsible Scraping

To ensure ethical and safe scraping:

A delay of time.sleep(1) is applied between requests
robots.txt is checked before initiating scraping
Request rate is kept low to avoid server overload
No aggressive or parallel request flooding is used
## 5. Data Storage Strategy
All scraped data is stored in structured JSON format
Each record is validated before saving
Data is kept consistent for easy querying, processing, and reuse