# Link Checker Script - Code Walkthrough

This document provides a detailed explanation of the `link_checker.py` script, which is responsible for fetching URLs, extracting text, and checking for specific keywords.

## 1. Imports and Configuration

```python
import requests
from bs4 import BeautifulSoup
import csv
...
```
- **`requests`**: Standard library for making HTTP requests (fetching web pages).
- **`bs4` (BeautifulSoup)**: Used for parsing HTML and extracting visible text.
- **`ssl` & `HTTPAdapter`**: Used to customize how SSL/TLS connections are handled (crucial for accessing older government or legacy sites).
- **`ThreadPoolExecutor`**: Allows processing multiple URLs in parallel to speed up the script.
- **`re`**: Regular expressions for advanced keyword matching.

### Target Keywords
```python
TARGET_KEYWORDS = [ ... ]
```
- This list defines what the script looks for in the text. If any of these words are found, the link is marked as "Relevant".

---

## 2. Class: `LegacySSLAdapter`

**Purpose**: Many older websites (especially government ones) use outdated SSL protocols (TLS 1.0/1.1) that modern Python blocks by default. This class forces Python to accept them.

- **`init_poolmanager`**:
    - `context = ssl.create_default_context()`: Creates a standard SSL setting.
    - `context.check_hostname = False`: Disables hostname checking (allows mismatched certificates).
    - `context.verify_mode = ssl.CERT_NONE`: Disables certificate verification (accepts self-signed or expired certs).
    - `context.options &= ~ssl.OP_NO_TLSv1`: Explicitly *allows* TLS 1.0/1.1 by removing the "Block TLSv1" flag.

---

## 3. Class: `DataFetcher`

**Purpose**: Handles all network-related operations. It tries multiple methods to get the HTML content of a page.

### `__init__`
- Sets up **User-Agent headers** to mimic a real Chrome browser on macOS. This helps avoid being blocked by anti-bot systems.

### `resolve_url(self, url)`
- Checks if the URL is a Google News Redirect (`news.google.com`).
- Uses `googlenewsdecoder` to find the *real* source URL (e.g., `timesofindia.com/...`) so we check the actual site.

### `fetch_content(self, url)`
This is the core fetching logic with a **3-Layer Fallback Strategy**:

1.  **Attempt 1: Standard `requests`**
    - Uses a `Session` with the `LegacySSLAdapter`.
    - Tries to get the page with a 20-second timeout.
    - Checks if content length is < 800 bytes (often means a "You are blocked" or "Enable JS" page).

2.  **Attempt 2: `cloudscraper`**
    - If standard requests fail (403 Forbidden, 429 Too Many Requests), it tries `cloudscraper`.
    - `cloudscraper` is designed to bypass Cloudflare's "I'm under attack" mode and other bot protections.

3.  **Attempt 3: System `cURL`**
    - If Python methods fail (often due to deep SSL handshake issues), it calls the command-line tool `curl`.
    - `curl -L -k`: Follows redirects (`-L`) and ignores SSL errors (`-k`).
    - This is the "nuclear option" that usually works if the server is up.

---

## 4. Class: `DataProcessor`

**Purpose**: Once we have the raw HTML from `DataFetcher`, this class makes sense of it.

### `extract_text(self, html_content)`
- **`BeautifulSoup(..., 'html.parser')`**: Parses the raw HTML bytes.
- **`script.decompose()`**: Removes `<script>`, `<style>`, `<nav>`, `<footer`> tags. We don't want to check keywords in the website menu or footer code, only the article body.
- **`get_text`**: Extracts the visible text.

### `analyze_relevance(self, text, main_keywords, ...)`
- **Logic**:
    1.  Iterates through `main_keywords`.
    2.  Uses `re.findall` with `\b` (word boundaries) to ensure we match "FSS" but not "Professional" (if searching for FSS).
    3.  If any keyword is found, returns **"Relevant"**.
    4.  If none found, returns **"Irrelevant"**.

### `load_links(self, input_dir)`
- Scans the `input_data/` folder.
- Picks the first `.csv` or `.txt` file it finds.
- Reads line-by-line (or row-by-row for CSV) to build a list of URLs to check.

---

## 5. Main Execution Flow

### `process_single_url_task`
- This code creates a single "job" that:
    1.  Calls `fetcher.fetch_content(url)` -> Gets HTML.
    2.  Calls `processor.extract_text(...)` -> Gets Text.
    3.  Calls `processor.analyze_relevance(...)` -> Checks Keywords.
    4.  **Fallback Check**: If no keywords found in text, it checks if the **URL itself** contains the keyword (e.g., `.../news/pradan-NGO-award.html`).

### `main()`
1.  Initializes `DataFetcher` and `DataProcessor`.
2.  Loads links from `input_data/`.
3.  Opens `output_data/link_report.csv` for writing.
4.  **`ThreadPoolExecutor(max_workers=10)`**:
    - Starts 10 concurrent threads.
    - Each thread takes a URL and runs `process_single_url_task`.
    - This allows checking 10 sites at once instead of one by one.
5.  Writes results (URL, Status, Match Count) to the CSV file immediately.

---

## Summary
- **Robustness**: The script tries very hard to get the page (Requests -> Cloudscraper -> cURL).
- **Accuracy**: It cleans the HTML (removing menus/ads) before checking keywords.
- **Security**: It handles old SSL sites that usually crash Python scripts.
