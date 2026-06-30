# DECISIONS.md

## 1. JSON Schema (judgments.json)

Each record contains:

- serial_number (string)
- case (string)
- remarks (string)
- other_citation (string)
- phc_neutral_citation (string)
- decision_date (string)
- sc_status (string)
- category (string)
- scraped_at (string)
- id (string)
- pdf_path (string)
---

## 2. Idempotency
Duplicate prevention is handled using:
- phc_neutral_citation as unique key

---

## 3. Scheduling
APScheduler is used for automated scraping.

---

## 4. Site Etiquette
- Added time.sleep(1) between requests
- Checked robots.txt before scraping
- Avoid aggressive requests

---

## 5. Data Storage
All data stored in structured JSON format.