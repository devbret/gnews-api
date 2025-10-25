# GNews API Tool

The first Python script fetches recent articles based on user-defined keywords, languages and countries, then logs the progress of each API request. It saves the results as a human-readable text file containing titles, sources, publication dates, URLs, descriptions and article content.

The script described above also handles retries, rate limits and pagination automatically, ensuring reliable performance even when fetching large amounts of data across multiple keywords or pages. The second script is a companion cleaner for processing the output text file and extracting only the relevant, human-readable values from each article.

Specifically, it isolates and outputs the title, source, description and content fields for every article. The result is a simplified .txt file which is easy to read or use for further natural language processing or summarization tasks.

Together, these two scripts form a lightweight, end-to-end pipeline for gathering and preparing real-world news content for analysis.
