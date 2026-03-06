import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    keywords: List[str]
    lang: str
    country: str
    max_per_page: int
    pages: int
    output_file: str
    log_file: str
    timeout_sec: int = 15
    page_delay_sec: float = 0.3
    keyword_delay_sec: float = 0.5


def load_config() -> Config:
    load_dotenv()

    api_key = os.getenv("GNEWS_API_KEY", "").strip()
    base_url = os.getenv("GNEWS_BASE_URL", "https://gnews.io/api/v4/search").strip()

    env_keywords = os.getenv("GNEWS_KEYWORDS")
    keywords = (
        [k.strip() for k in env_keywords.split(",") if k.strip()]
        if env_keywords
        else ["news"]
    )

    lang = os.getenv("GNEWS_LANG", "en").strip()
    country = os.getenv("GNEWS_COUNTRY", "us").strip()
    max_per_page = int(os.getenv("GNEWS_MAX", "100"))
    pages = int(os.getenv("GNEWS_PAGES", "1"))
    output_file = os.getenv("GNEWS_OUT", "gnews_results.txt").strip()
    log_file = os.getenv("GNEWS_LOG", "gnews_log.txt").strip()

    return Config(
        api_key=api_key,
        base_url=base_url,
        keywords=keywords,
        lang=lang,
        country=country,
        max_per_page=max_per_page,
        pages=pages,
        output_file=output_file,
        log_file=log_file,
    )


def setup_logging(log_file: str) -> logging.Logger:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("gnews_fetcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


def build_session() -> requests.Session:
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

    session = requests.Session()
    session.headers.update({"User-Agent": "GNewsFetcher/1.0"})
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_article(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": raw.get("title") or "No Title",
        "url": raw.get("url"),
        "source": (raw.get("source") or {}).get("name") or "Unknown Source",
        "publishedAt": raw.get("publishedAt") or "Unknown Date",
        "description": raw.get("description") or "",
        "content": raw.get("content") or "",
        "image": raw.get("image"),
    }


def fetch_news(
    session: requests.Session,
    config: Config,
    logger: logging.Logger,
    keyword: str,
    page: int,
) -> Optional[Dict[str, Any]]:
    params = {
        "q": keyword,
        "lang": config.lang,
        "country": config.country,
        "max": config.max_per_page,
        "page": page,
        "apikey": config.api_key,
        "expand": "content",
    }

    call_start = time.perf_counter()
    logger.info("API call started for keyword='%s', page=%s", keyword, page)

    try:
        resp = session.get(config.base_url, params=params, timeout=config.timeout_sec)

        try:
            body = resp.json()
        except ValueError:
            body = None

        if resp.status_code != 200:
            api_err = body.get("errors") if isinstance(body, dict) else None
            raise requests.HTTPError(
                f"HTTP {resp.status_code} {api_err or resp.text[:200]}"
            )

        duration = time.perf_counter() - call_start
        logger.info(
            "API call completed for keyword='%s', page=%s in %.2fs",
            keyword,
            page,
            duration,
        )
        return body

    except requests.RequestException as exc:
        logger.error("ERROR for keyword='%s', page=%s: %s", keyword, page, exc)
        return None


def collect_articles(
    session: requests.Session,
    config: Config,
    logger: logging.Logger,
) -> List[Dict[str, Any]]:
    seen_urls: Set[str] = set()
    collected: List[Dict[str, Any]] = []

    for keyword in config.keywords:
        logger.info("--- Fetching articles for: '%s' ---", keyword)

        for page in range(1, config.pages + 1):
            data = fetch_news(session, config, logger, keyword, page)
            if not data:
                continue

            articles = data.get("articles", []) or []
            logger.info(
                "Received %s articles for kw='%s', page=%s",
                len(articles),
                keyword,
                page,
            )

            for raw_article in articles:
                article = normalize_article(raw_article)
                url = (article.get("url") or "").strip()

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                article["keyword"] = keyword
                collected.append(article)

            if len(articles) < config.max_per_page:
                break

            time.sleep(config.page_delay_sec)

        time.sleep(config.keyword_delay_sec)

    return collected


def write_articles(
    config: Config,
    logger: logging.Logger,
    articles: List[Dict[str, Any]],
    finished: str,
) -> None:
    Path(config.output_file).parent.mkdir(parents=True, exist_ok=True)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        keyword = str(article.get("keyword") or "unknown")
        grouped.setdefault(keyword, []).append(article)

    with open(config.output_file, "w", encoding="utf-8") as f:
        f.write(f"GNews Fetch Run — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Language: {config.lang} | Country: {config.country}\n")
        f.write(f"Keywords: {', '.join(config.keywords)}\n")
        f.write("=" * 60 + "\n\n")

        for keyword in config.keywords:
            f.write(f"\n### Keyword: {keyword}\n")
            f.write("-" * 60 + "\n")

            for article in grouped.get(keyword, []):
                f.write(f"Title: {article['title']}\n")
                f.write(f"Source: {article['source']}\n")
                f.write(f"Published: {article['publishedAt']}\n")
                f.write(f"URL: {article['url']}\n")

                if article["description"]:
                    f.write(f"Description: {article['description']}\n")
                if article["content"]:
                    f.write(f"Content: {article['content']}\n")

                f.write("-" * 60 + "\n")

        f.write(f"\nRun Finished: {finished}\n")
        f.write(f"Total Articles Written: {len(articles)}\n")

    logger.info("Wrote %s articles to: %s", len(articles), config.output_file)


def main() -> None:
    config = load_config()
    logger = setup_logging(config.log_file)

    if not config.api_key:
        logger.critical("GNEWS_API_KEY is missing (check your .env).")
        raise SystemExit(1)

    run_started = utc_now_iso()
    logger.info("=== GNews Keyword Fetch Started ===")
    logger.info("Run started (UTC): %s", run_started)
    logger.info("Keywords: %s", config.keywords)
    logger.info(
        "Lang=%s, Country=%s, Pages=%s, Max/pg=%s",
        config.lang,
        config.country,
        config.pages,
        config.max_per_page,
    )

    script_start = time.perf_counter()

    with build_session() as session:
        articles = collect_articles(session, config, logger)

    finished = utc_now_iso()
    duration = time.perf_counter() - script_start

    write_articles(config, logger, articles, finished)

    logger.info("=== GNews Keyword Fetch Complete in %.2f seconds ===", duration)


if __name__ == "__main__":
    main()