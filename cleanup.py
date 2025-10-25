import re
import argparse
from pathlib import Path

FIELD_ORDER = ["Title", "Source", "Content"]

def is_separator(line: str) -> bool:
    s = line.strip()
    return s and set(s) == {"-"} and len(s) >= 20

def parse_file(text: str):
    field_re = re.compile(r'^(Title|Source|Published|URL|Content):\s*(.*)$')
    articles = []
    current = {k: "" for k in FIELD_ORDER}
    current_field = None
    lines = text.splitlines()

    def flush_article():
        nonlocal current
        if any(current.get(k, "").strip() for k in FIELD_ORDER):
            articles.append([current.get(k, "").rstrip() for k in FIELD_ORDER])
        current = {k: "" for k in FIELD_ORDER}

    for raw in lines:
        line = raw.rstrip("\n")
        if is_separator(line):
            if any(current.values()):
                flush_article()
            current_field = None
            continue

        m = field_re.match(line)
        if m:
            fname, fval = m.group(1), m.group(2)
            if fname in FIELD_ORDER:
                current_field = fname
                current[fname] = fval.strip()
            else:
                current_field = None
            continue

        if current_field in FIELD_ORDER:
            if current[current_field]:
                current[current_field] += "\n" + line
            else:
                current[current_field] = line

    if any(current.values()):
        flush_article()
    return articles

def main():
    ap = argparse.ArgumentParser(description="Extract human-readable values from GNews .txt output.")
    ap.add_argument("-i", "--input", default="gnews_results.txt", help="Path to input .txt")
    ap.add_argument("-o", "--output", default="gnews_cleaned.txt", help="Path to output .txt")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    text = in_path.read_text(encoding="utf-8")
    articles = parse_file(text)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for idx, (title, source, content) in enumerate(articles, start=1):
            if title:    f.write(f"{title}\n")
            else:        f.write("\n")
            if source:   f.write(f"{source}\n")
            else:        f.write("\n")
            if content:  f.write(f"{content}\n")
            else:        f.write("\n")
            if idx < len(articles):
                f.write("\n")

if __name__ == "__main__":
    main()
