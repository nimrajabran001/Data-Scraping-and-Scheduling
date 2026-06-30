import os
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

# PDF Downloader with retry mechanism, Retries up to 3 times with 3 seconds delay if failed
@retry(stop=stop_after_attempt(3), wait=wait_fixed(3))
def download_pdf(url, folder, filename):

    if not url:
        return None

    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    
    # If file already exists, avoid re-downloading (idempotency)
    if os.path.exists(path):
        return path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Referer": "https://www.peshawarhighcourt.gov.pk/"
    }

    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()

    with open(path, "wb") as f:
        f.write(response.content)

    return path