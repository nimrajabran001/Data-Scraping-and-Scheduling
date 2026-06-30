# Project Overview

This project scrapes reported judgments from the Peshawar High Court website 
and stores them in structured JSON format.
It also downloads related PDF files and automates scraping using a scheduler.

# Features 
- Web scraping 
- Structured JSON output
- PDF download support
- Duplicate prevention using hashing
- Automated scheduling (APScheduler)
- Error handling and retries

##  Robots.txt Compliance

The scraper respects the website's robots.txt rules.
Checked at:
https://www.peshawarhighcourt.gov.pk/robots.txt
No restricted or disallowed paths are accessed.
The scraper only accesses publicly available pages.

## Clone repository
git clone https://github.com/nimrajabran001/Data-Scraping-and-Scheduling.git
cd  Data-Scraping-and-Scheduling


## Install dependencies 
pip install -r requirements.txt

## Run 
python Scraper.py
python scheduler.py

