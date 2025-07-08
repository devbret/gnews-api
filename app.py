import requests
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

# === CONFIGURATION ===
API_KEY = os.getenv("GNEWS_API_KEY")
BASE_URL = "https://gnews.io/api/v4/search"
KEYWORDS = ["keywords",]
OUTPUT_FILE = "gnews_results.txt"

# === FUNCTION ===
def fetch_news(keyword):
    params = {
        "q": keyword,
        "lang": "en",
        "country": "us",
        "max": 10,
        "apikey": API_KEY
    }
    try:
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[ERROR] Keyword: '{keyword}' - {e}")
        return None

# === MAIN SCRIPT ===
def main():
    all_results = []
    
    for keyword in KEYWORDS:
        print(f"[INFO] Fetching news for: '{keyword}'")
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

    print(f"\n✅ Saved {len(all_results)} keyword results to '{OUTPUT_FILE}'")

if __name__ == "__main__":
    main()