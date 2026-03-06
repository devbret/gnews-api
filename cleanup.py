import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

FIELD_ORDER = ["Title", "Source", "Content"]


@dataclass(frozen=True)
class Config:
    input_file: str
    output_file: str
    log_file: str


def load_config() -> Config:
    parser = argparse.ArgumentParser(
        description="Extract human-readable values from GNews .txt output."
    )
    parser.add_argument(
        "-i",
        "--input",
        default="gnews_results.txt",
        help="Path to input .txt",
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


def is_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) == {"-"} and len(stripped) >= 20


def flush_article(current: dict[str, str], articles: List[List[str]]) -> dict[str, str]:
    if any(current.get(field, "").strip() for field in FIELD_ORDER):
        articles.append([current.get(field, "").rstrip() for field in FIELD_ORDER])
    return {field: "" for field in FIELD_ORDER}


def parse_file(text: str, logger: Optional[logging.Logger] = None) -> List[List[str]]:
    field_re = re.compile(r"^(Title|Source|Published|URL|Content):\s*(.*)$")
    articles: List[List[str]] = []
    current = {field: "" for field in FIELD_ORDER}
    current_field: Optional[str] = None

    for line in text.splitlines():
        if is_separator(line):
            if any(current.values()):
                current = flush_article(current, articles)
            current_field = None
            continue

        match = field_re.match(line)
        if match:
            field_name, field_value = match.group(1), match.group(2)

            if field_name in FIELD_ORDER:
                current_field = field_name
                current[field_name] = field_value.strip()
            else:
                current_field = None

            continue

        if current_field in FIELD_ORDER:
            if current[current_field]:
                current[current_field] += "\n" + line
            else:
                current[current_field] = line

    if any(current.values()):
        current = flush_article(current, articles)

    if logger:
        logger.info("Parsed %s cleaned article(s) from input text", len(articles))

    return articles


def read_input(config: Config, logger: logging.Logger) -> str:
    input_path = Path(config.input_file)

    if not input_path.exists():
        logger.critical("Input file does not exist: %s", config.input_file)
        raise SystemExit(1)

    logger.info("Reading input file: %s", config.input_file)
    return input_path.read_text(encoding="utf-8")


def write_output(
    config: Config,
    logger: logging.Logger,
    articles: List[List[str]],
) -> None:
    output_path = Path(config.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Writing %s cleaned article(s) to: %s", len(articles), config.output_file)

    with output_path.open("w", encoding="utf-8") as file:
        for idx, (title, source, content) in enumerate(articles, start=1):
            file.write(f"{title}\n" if title else "\n")
            file.write(f"{source}\n" if source else "\n")
            file.write(f"{content}\n" if content else "\n")

            if idx < len(articles):
                file.write("\n")


def main() -> None:
    config = load_config()
    logger = setup_logging(config.log_file)

    logger.info("=== GNews cleanup started ===")
    logger.info("Input: %s", config.input_file)
    logger.info("Output: %s", config.output_file)

    text = read_input(config, logger)
    articles = parse_file(text, logger)
    write_output(config, logger, articles)

    logger.info("=== GNews cleanup complete ===")


if __name__ == "__main__":
    main()