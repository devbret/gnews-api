import json

input_file = "gnews_results.txt"
output_file = "extracted_articles.txt"

with open(input_file, "r", encoding="utf-8") as f:
    data = json.load(f)

with open(output_file, "w", encoding="utf-8") as out:
    for entry in data:
        for article in entry.get("articles", []):
            source_name = article.get("source", {}).get("name", "")
            title = article.get("title", "")
            description = article.get("description", "")
            content = article.get("content", "")
            
            line = f"{source_name}\n {title}\n {description}\n {content[:-10]}\n"
            out.write(line)

print(f"Extraction complete! Saved to: {output_file}")
