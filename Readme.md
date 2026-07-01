
# 📘 Project Decisions Document

## Overview

This document outlines the key design decisions, architecture choices, and implementation strategies used in the Data Scraping and Scheduling project.

---

## 1. Data Schema (`judgments.json`)

All scraped records are stored in a structured JSON format to ensure consistency, scalability, and easy processing.

### 📄 Schema Definition

Each record contains the following fields:

* `serial_number` *(string)* — Case serial number
* `case` *(string)* — Case title or description
* `remarks` *(string)* — Additional notes or observations
* `other_citation` *(string)* — Alternative citation reference
* `phc_neutral_citation` *(string)* — Primary unique citation identifier
* `decision_date` *(string)* — Date of judgment/decision
* `sc_status` *(string)* — Supreme Court status indicator
* `category` *(string)* — Case classification/category
* `scraped_at` *(string)* — Timestamp when data was scraped
* `id` *(string)* — Unique internal identifier
* `pdf_path` *(string)* — File path of stored PDF document

---

## 2. Idempotency & Duplicate Handling

To prevent duplicate records during repeated scraping runs:

* **Primary uniqueness key:** `phc_neutral_citation`
* Before inserting new data, existing records are checked using this key
* Ensures **no duplicate entries** even across multiple scheduled runs

---

## 3. Scheduling & Automation

The project uses **APScheduler** to automate scraping tasks.

### Features:

* Scheduled scraping at defined intervals
* Background job execution
* Continuous data collection without manual intervention

---

## 4. Ethical Scraping & Site Etiquette

To ensure responsible and non-intrusive scraping:

* A delay of `time.sleep(1)` is applied between requests
* `robots.txt` is checked before scraping any endpoint
* Request frequency is intentionally kept low
* No concurrent request flooding or aggressive crawling is used

---

## 5. Data Storage Strategy

* All scraped data is stored in **structured JSON format**
* Each record is validated before saving
* Data is designed for:

  * Easy parsing
  * Future database migration
  * Analytics and reporting

---

## 6. System Design Summary (Architecture)

```
Scheduler (APScheduler)
        ↓
Scraper Engine
        ↓
HTML Parsing & Data Extraction
        ↓
Validation & Deduplication
        ↓
JSON Storage (judgments.json)
        ↓
PDF Downloader (if available)
```

---

## 7. Key Design Goals

* ✔ Reliability (no duplicate data)
* ✔ Scalability (supports scheduled scraping)
* ✔ Maintainability (clean structured JSON)
* ✔ Ethical compliance (rate limiting + robots.txt check)

---

If you want next upgrade, I can also help you:

* turn this into a **full professional README with badges + screenshots**
* add **GitHub project description (for submission dashboard)**
* or create a **system architecture diagram image (for marks boost)**
