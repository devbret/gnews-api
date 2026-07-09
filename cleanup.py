import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class Config:
    input_file: str
    output_file: str
    log_file: str


def load_config() -> Config:
    parser = argparse.ArgumentParser(
        description="Extract human-readable values from GNews .json output."
    )
    parser.add_argument(
        "-i",
        "--input",
        default="gnews_results.json",
        help="Path to input .json",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="gnews_cleaned.txt",
        help="Path to output .txt",
    )
    parser.add_argument(
        "-l",
        "--log",
        default="gnews_cleaned.log",
        help="Path to log file",
    )
    args = parser.parse_args()

    return Config(
        input_file=args.input,
        output_file=args.output,
        log_file=args.log,
    )


def setup_logging(log_file: str) -> logging.Logger:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("gnews_cleanup")
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


def read_articles(config: Config, logger: logging.Logger) -> List[Dict[str, Any]]:
    input_path = Path(config.input_file)

    if not input_path.exists():
        logger.critical("Input file does not exist: %s", config.input_file)
        raise SystemExit(1)

    logger.info("Reading input file: %s", config.input_file)

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.critical("Input file is not valid JSON: %s", exc)
        raise SystemExit(1)

    articles = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(articles, list):
        logger.critical("No article list found in: %s", config.input_file)
        raise SystemExit(1)

    logger.info("Loaded %s article(s) from input file", len(articles))
    return articles


def write_output(
    config: Config,
    logger: logging.Logger,
    articles: List[Dict[str, Any]],
) -> None:
    output_path = Path(config.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Writing %s cleaned article(s) to: %s", len(articles), config.output_file)

    with output_path.open("w", encoding="utf-8") as file:
        for idx, article in enumerate(articles, start=1):
            file.write(f"{article.get('title') or ''}\n")
            file.write(f"{article.get('source') or ''}\n")
            file.write(f"{article.get('content') or ''}\n")

            if idx < len(articles):
                file.write("\n")


def main() -> None:
    config = load_config()
    logger = setup_logging(config.log_file)

    logger.info("=== GNews cleanup started ===")
    logger.info("Input: %s", config.input_file)
    logger.info("Output: %s", config.output_file)

    articles = read_articles(config, logger)
    write_output(config, logger, articles)

    logger.info("=== GNews cleanup complete ===")


if __name__ == "__main__":
    main()
