import requests
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# === CONFIGURATION ===
API_KEY = os.getenv("GNEWS_API_KEY")
BASE_URL = "https://gnews.io/api/v4/search"
KEYWORDS = ["keyword","keyword"]
OUTPUT_FILE = "gnews_results.txt"
LOG_FILE = "gnews_log.txt"

# === LOGGING FUNCTION ===
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(log_line + "\n")

# === FETCH FUNCTION ===
def fetch_news(keyword):
    params = {
        "q": keyword,
        "lang": "en",
        "country": "us",
        "max": 100,
        "apikey": API_KEY,
        "expand": "content"
    }
    try:
        call_start = time.time()
        log(f"API call started for keyword: '{keyword}'")
        
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        
        call_end = time.time()
        duration = round(call_end - call_start, 2)
        log(f"API call completed for keyword: '{keyword}' in {duration} seconds")

        return response.json()
    except requests.RequestException as e:
        log(f"ERROR for keyword '{keyword}': {e}")
        return None

# === MAIN SCRIPT ===
def main():
    all_results = []

    log("=== GNews Keyword Fetch Started ===")
    script_start = datetime.now()

    for keyword in KEYWORDS:
        log(f"--- Fetching articles for: '{keyword}' ---")
        data = fetch_news(keyword)
        
        if data:
            all_results.append({
                "keyword": keyword,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "articles": data.get("articles", [])
            })
        
        time.sleep(2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(all_results, indent=2, ensure_ascii=False))

    script_end = datetime.now()
    total_duration = (script_end - script_start).total_seconds()
    log(f"=== GNews Keyword Fetch Complete in {total_duration:.2f} seconds ===")
    log(f"Results saved to: {OUTPUT_FILE}\n")

if __name__ == "__main__":
    main()
