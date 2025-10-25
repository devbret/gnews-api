import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GNEWS_API_KEY")
BASE_URL = os.getenv("GNEWS_BASE_URL", "https://gnews.io/api/v4/search")
ENV_KEYWORDS = os.getenv("GNEWS_KEYWORDS")
KEYWORDS = (
    [k.strip() for k in ENV_KEYWORDS.split(",") if k.strip()]
    if ENV_KEYWORDS
    else ["news"]
)
LANG = os.getenv("GNEWS_LANG", "en")
COUNTRY = os.getenv("GNEWS_COUNTRY", "us")
MAX_PER_PAGE = int(os.getenv("GNEWS_MAX", "100"))
PAGES = int(os.getenv("GNEWS_PAGES", "1"))
OUTPUT_FILE = os.getenv("GNEWS_OUT", "gnews_results.txt")
LOG_FILE = os.getenv("GNEWS_LOG", "gnews_log.txt")

def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def build_session(timeout_sec: int = 15) -> requests.Session:
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.headers.update({"User-Agent": "GNewsFetcher/1.0"})
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    original = s.request
    def _with_timeout(method, url, **kwargs):
        kwargs.setdefault("timeout", timeout_sec)
        return original(method, url, **kwargs)
    s.request = _with_timeout
    return s

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def normalize_article(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": raw.get("title"),
        "url": raw.get("url"),
        "source": (raw.get("source") or {}).get("name"),
        "publishedAt": raw.get("publishedAt"),
        "description": raw.get("description"),
        "content": raw.get("content"),
        "image": raw.get("image"),
        "raw": raw,
    }

def fetch_news(session: requests.Session, keyword: str, page: int) -> Optional[Dict[str, Any]]:
    params = {
        "q": keyword,
        "lang": LANG,
        "country": COUNTRY,
        "max": MAX_PER_PAGE,
        "page": page,
        "apikey": API_KEY,
        "expand": "content",
    }
    call_start = time.time()
    log(f"API call started for keyword='{keyword}', page={page}")
    try:
        resp = session.get(BASE_URL, params=params)
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code != 200:
            api_err = body.get("errors") if isinstance(body, dict) else None
            raise requests.HTTPError(f"HTTP {resp.status_code} {api_err or resp.text[:200]}")
        duration = round(time.time() - call_start, 2)
        log(f"API call completed for keyword='{keyword}', page={page} in {duration}s")
        return body
    except requests.RequestException as e:
        log(f"ERROR for keyword='{keyword}', page={page}: {e}")
        return None

def main() -> None:
    if not API_KEY:
        log("FATAL: GNEWS_API_KEY is missing (check your .env).")
        raise SystemExit(1)
    session = build_session()
    seen_urls: Set[str] = set()
    run_started = utc_now_iso()
    log("=== GNews Keyword Fetch Started ===")
    log(f"Run started (UTC): {run_started}")
    log(f"Keywords: {KEYWORDS}")
    log(f"Lang={LANG}, Country={COUNTRY}, Pages={PAGES}, Max/pg={MAX_PER_PAGE}")
    total_written = 0
    script_start = time.time()
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"GNews Fetch Run — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Language: {LANG} | Country: {COUNTRY}\n")
        f.write(f"Keywords: {', '.join(KEYWORDS)}\n")
        f.write("=" * 60 + "\n\n")
        for keyword in KEYWORDS:
            log(f"--- Fetching articles for: '{keyword}' ---")
            f.write(f"\n### Keyword: {keyword}\n")
            f.write("-" * 60 + "\n")
            for page in range(1, PAGES + 1):
                data = fetch_news(session, keyword, page)
                if not data:
                    continue
                articles = data.get("articles", []) or []
                log(f"Received {len(articles)} articles for kw='{keyword}', page={page}")
                for a in articles:
                    url = (a.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = a.get("title") or "No Title"
                    source = (a.get("source") or {}).get("name") or "Unknown Source"
                    published = a.get("publishedAt") or "Unknown Date"
                    description = a.get("description") or ""
                    content = a.get("content") or ""
                    f.write(f"Title: {title}\n")
                    f.write(f"Source: {source}\n")
                    f.write(f"Published: {published}\n")
                    f.write(f"URL: {url}\n")
                    if description:
                        f.write(f"Description: {description}\n")
                    if content:
                        f.write(f"Content: {content}\n")
                    f.write("-" * 60 + "\n")
                    total_written += 1
                if len(articles) < MAX_PER_PAGE:
                    break
                time.sleep(0.3)
            time.sleep(0.5)
        duration = round(time.time() - script_start, 2)
        finished = utc_now_iso()
        f.write(f"\nRun Finished: {finished}\n")
        f.write(f"Total Articles Written: {total_written}\n")
    log(f"=== GNews Keyword Fetch Complete in {duration:.2f} seconds ===")
    log(f"Wrote {total_written} articles to: {OUTPUT_FILE}\n")

if __name__ == "__main__":
    main()
