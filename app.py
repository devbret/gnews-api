import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    endpoint: str
    category: str
    keywords: List[str]
    lang: str
    country: str
    max_per_page: int
    pages: int
    json_file: str
    output_file: str
    log_file: str
    timeout_sec: int
    page_delay_sec: float
    keyword_delay_sec: float


@dataclass(frozen=True)
class RunResult:
    articles: List[Dict[str, Any]]
    status: str


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"Config error: {name} must be an integer, got {raw!r}.")
    if value < minimum:
        raise SystemExit(f"Config error: {name} must be >= {minimum}, got {value}.")
    return value


def _env_float(name: str, default: float, minimum: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit(f"Config error: {name} must be a number, got {raw!r}.")
    if value < minimum:
        raise SystemExit(f"Config error: {name} must be >= {minimum}, got {value}.")
    return value


def load_config() -> Config:
    load_dotenv()

    api_key = os.getenv("GNEWS_API_KEY", "").strip()
    base_url = os.getenv("GNEWS_BASE_URL", "https://gnews.io/api/v4").strip()

    endpoint = (os.getenv("GNEWS_ENDPOINT") or "search").strip() or "search"
    if endpoint not in ("search", "top-headlines"):
        raise SystemExit(
            f"Config error: GNEWS_ENDPOINT must be 'search' or 'top-headlines', "
            f"got {endpoint!r}."
        )
    category = (os.getenv("GNEWS_CATEGORY") or "").strip()

    env_keywords = os.getenv("GNEWS_KEYWORDS")
    keywords = (
        [k.strip() for k in env_keywords.split(",") if k.strip()]
        if env_keywords
        else []
    )
    if not keywords:
        keywords = [""] if endpoint == "top-headlines" else ["news"]

    lang = os.getenv("GNEWS_LANG", "en").strip()
    country = os.getenv("GNEWS_COUNTRY", "us").strip()
    max_per_page = _env_int("GNEWS_MAX", 100, minimum=1)
    pages = _env_int("GNEWS_PAGES", 1, minimum=1)
    json_file = os.getenv("GNEWS_JSON", "gnews_results.json").strip()
    output_file = os.getenv("GNEWS_OUT", "gnews_results.txt").strip()
    log_file = os.getenv("GNEWS_LOG", "gnews_log.txt").strip()
    timeout_sec = _env_int("GNEWS_TIMEOUT", 15, minimum=1)
    page_delay_sec = _env_float("GNEWS_PAGE_DELAY", 0.3, minimum=0.0)
    keyword_delay_sec = _env_float("GNEWS_KEYWORD_DELAY", 0.5, minimum=0.0)

    return Config(
        api_key=api_key,
        base_url=base_url,
        endpoint=endpoint,
        category=category,
        keywords=keywords,
        lang=lang,
        country=country,
        max_per_page=max_per_page,
        pages=pages,
        json_file=json_file,
        output_file=output_file,
        log_file=log_file,
        timeout_sec=timeout_sec,
        page_delay_sec=page_delay_sec,
        keyword_delay_sec=keyword_delay_sec,
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
    url = f"{config.base_url.rstrip('/')}/{config.endpoint}"
    params: Dict[str, Any] = {
        "lang": config.lang,
        "country": config.country,
        "max": config.max_per_page,
        "page": page,
        "apikey": config.api_key,
        "expand": "content",
    }
    if keyword:
        params["q"] = keyword
    if config.endpoint == "top-headlines" and config.category:
        params["category"] = config.category

    call_start = time.perf_counter()
    logger.info("API call started for keyword='%s', page=%s", keyword, page)

    try:
        resp = session.get(url, params=params, timeout=config.timeout_sec)

        try:
            body = resp.json()
        except ValueError:
            body = None

        if resp.status_code in (401, 403):
            api_err = body.get("errors") if isinstance(body, dict) else None
            raise AuthError(f"HTTP {resp.status_code} {api_err or resp.text[:200]}")

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
        message = str(exc)
        if config.api_key:
            message = message.replace(config.api_key, "***")
        logger.error("ERROR for keyword='%s', page=%s: %s", keyword, page, message)
        return None


def collect_articles(
    session: requests.Session,
    config: Config,
    logger: logging.Logger,
) -> RunResult:
    seen_by_url: Dict[str, Dict[str, Any]] = {}
    collected: List[Dict[str, Any]] = []
    status = "completed"

    try:
        for keyword in config.keywords:
            label = keyword or config.category or "top-headlines"
            logger.info("--- Fetching articles for: '%s' ---", label)

            for page in range(1, config.pages + 1):
                data = fetch_news(session, config, logger, keyword, page)
                if not data:
                    continue

                articles = data.get("articles", []) or []
                logger.info(
                    "Received %s articles for kw='%s', page=%s",
                    len(articles),
                    label,
                    page,
                )

                for raw_article in articles:
                    article = normalize_article(raw_article)
                    url = (article.get("url") or "").strip()

                    if not url:
                        continue

                    existing = seen_by_url.get(url)
                    if existing is not None:
                        if label not in existing["keywords"]:
                            existing["keywords"].append(label)
                        continue

                    article["keywords"] = [label]
                    seen_by_url[url] = article
                    collected.append(article)

                if len(articles) < config.max_per_page:
                    break

                time.sleep(config.page_delay_sec)

            time.sleep(config.keyword_delay_sec)

    except AuthError as exc:
        logger.critical("Aborting run, GNews rejected the request: %s", exc)
        status = "auth_failed"
    except KeyboardInterrupt:
        logger.warning(
            "Interrupted, keeping %s article(s) collected so far", len(collected)
        )
        status = "interrupted"

    return RunResult(articles=collected, status=status)


def write_json(
    config: Config,
    logger: logging.Logger,
    articles: List[Dict[str, Any]],
    started: str,
    finished: str,
    status: str,
) -> None:
    json_path = Path(config.json_file)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    run_meta: Dict[str, Any] = {
        "started": started,
        "finished": finished,
        "status": status,
        "endpoint": config.endpoint,
        "lang": config.lang,
        "country": config.country,
        "keywords": [k for k in config.keywords if k],
        "total_articles": len(articles),
    }
    if config.endpoint == "top-headlines":
        run_meta["category"] = config.category or "general"

    payload = {"run": run_meta, "articles": articles}

    tmp_path = json_path.with_name(json_path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, json_path)

    logger.info("Wrote %s articles to: %s", len(articles), config.json_file)


def write_articles(
    config: Config,
    logger: logging.Logger,
    articles: List[Dict[str, Any]],
    finished: str,
) -> None:
    Path(config.output_file).parent.mkdir(parents=True, exist_ok=True)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for article in articles:
        label = str((article.get("keywords") or ["unknown"])[0])
        grouped.setdefault(label, []).append(article)

    with open(config.output_file, "w", encoding="utf-8") as f:
        f.write(f"GNews Fetch Run - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Language: {config.lang} | Country: {config.country}\n")
        if config.endpoint == "top-headlines":
            f.write(
                f"Endpoint: top-headlines | Category: {config.category or 'general'}\n"
            )
        keywords_line = ", ".join(k for k in config.keywords if k)
        if keywords_line:
            f.write(f"Keywords: {keywords_line}\n")
        f.write("=" * 60 + "\n\n")

        for label, group in grouped.items():
            f.write(f"\n### Keyword: {label}\n")
            f.write("-" * 60 + "\n")

            for article in group:
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
    logger.info("Endpoint: %s", config.endpoint)
    logger.info("Keywords: %s", [k for k in config.keywords if k])
    logger.info(
        "Lang=%s, Country=%s, Pages=%s, Max/pg=%s",
        config.lang,
        config.country,
        config.pages,
        config.max_per_page,
    )

    script_start = time.perf_counter()

    with build_session() as session:
        result = collect_articles(session, config, logger)

    finished = utc_now_iso()
    duration = time.perf_counter() - script_start

    write_json(config, logger, result.articles, run_started, finished, result.status)
    write_articles(config, logger, result.articles, finished)

    if result.status == "completed":
        logger.info("=== GNews Keyword Fetch Complete in %.2f seconds ===", duration)
    else:
        logger.warning(
            "=== GNews Keyword Fetch ended early (%s) after %.2f seconds ===",
            result.status,
            duration,
        )
        raise SystemExit(130 if result.status == "interrupted" else 1)


if __name__ == "__main__":
    main()