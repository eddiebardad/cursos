# Course Scraper Wiki

Welcome to the Course Scraper documentation! This wiki provides extensive guidance on how the software works, deep-dive architectural overviews, practical use cases, and commands.

[TOC]

---

## 1. Overview & Use Cases

The Course Scraper is a scalable web scraping architecture designed specifically to extract educational course metadata from various online learning platforms (e.g., NetAcad, Aprende.org) and generic catalogs.

It normalizes this diverse, messy data into a flat, Schema.org-compliant CSV format, which is perfect for importing into content management systems like **Omeka S**.

### Common Use Cases

*   **Building a Centralized Course Catalog:** You manage an Omeka S instance and want to aggregate courses from multiple third-party providers (like Hubspot Academy, Cisco NetAcad, or local university portals) into one unified search interface.
*   **Data Migration & Archiving:** You need to extract course data from an old, legacy learning management system (LMS) into a structured CSV format for archiving or migrating to a new platform.
*   **Market Research:** You want to scrape publicly available course catalogs to analyze pricing trends, course durations, and popular keywords across different educational providers.
*   **Handling Difficult SPAs:** You need to scrape a modern website built with React, Angular, or Vue (Single Page Applications) where traditional scrapers fail because the content is loaded dynamically via JavaScript. This scraper's `--render` mode handles this effortlessly.

---

## 2. How the Software Works

The scraper is built on a highly modular architecture. Understanding this flow will help you use the tool more effectively and extend it when necessary.

### The Execution Flow

1.  **CLI Invocation (`cli.py`)**: The user runs a command. The CLI parses arguments like the target URL, the maximum number of pages to crawl, and whether to use JavaScript rendering.
2.  **Provider Detection**: The software inspects the URL. If it matches a known provider (e.g., `netacad.com`), it hands control to that specific adapter. If not, it uses the Generic Crawler.
3.  **Data Extraction**:
    *   *Generic Crawler*: Uses Breadth-First Search (BFS) to discover links on the same domain. It fetches HTML and passes it to the `parser.py`, which looks for Schema.org JSON-LD, Microdata, or OpenGraph tags.
    *   *Provider Adapter*: Uses custom logic (e.g., querying a hidden API directly, or navigating a specific sitemap) to extract the data with surgical precision.
4.  **Schema Validation (`loader.py` & `models.py`)**: As raw data is extracted, it is passed into the `Course` model. This model is **dynamically generated** from the official Schema.org RDF vocabulary. It ensures types are correct (e.g., `price` is a number) and validates formats (e.g., `timeRequired` must be ISO 8601).
5.  **Exporting**: The validated Pydantic models are passed to the `CSVExporter`, which flattens the nested data into a simple CSV structure.

---

## 3. Installation

Ensure you have **Python 3.9+** installed. We recommend using a modern Python package manager like `uv`.

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Install Playwright (Required for `--render` mode):**
   If you intend to scrape dynamic websites, you must install the Playwright browser binaries:
   ```bash
   playwright install chromium
   ```

---

## 4. Using the Command-Line Interface (CLI)

The `cli.py` script is your primary tool. It provides a clean interface for controlling the scraping process.

### Syntax
```bash
python cli.py --url <URL> [OPTIONS]
```

### Options Explained

*   `--url TEXT` **(Required)**: The starting URL. This can be a single course page, a catalog, or a homepage.
*   `--output TEXT`: The output file path. Defaults to `results.csv`. Use `.json` to output raw JSON-LD instead.
*   `--provider TEXT`: Force a specific adapter (e.g., `Netacad`). Usually unnecessary as the software auto-detects this.
*   `--render / --no-render`: Enables the Playwright engine to execute JavaScript. **Crucial for modern React/Vue sites.** (Default: `--no-render`).
*   `--max-pages INTEGER`: Limits the spider. If set to 50, the scraper will stop after scanning 50 pages or extracting ~500 courses. (Default: 100).

### Practical Examples

**Scenario A: Scraping a traditional, static university website**
```bash
python cli.py --url "https://example-university.edu/catalog" --max-pages 200 --output uni_courses.csv
```
*Result:* The generic spider crawls 200 pages, extracting JSON-LD course data instantly.

**Scenario B: Scraping a modern Single Page Application (SPA)**
```bash
python cli.py --url "https://modern-lms.com/explore" --render --max-pages 50 --output modern.csv
```
*Result:* Playwright boots up an invisible Chromium browser, executes the site's React code, waits for the courses to appear, and then extracts them.

**Scenario C: Using a specialized provider (e.g., Aprende.org)**
```bash
python cli.py --url "https://aprende.org/" --output aprende.csv
```
*Result:* The CLI detects `aprende.org`, bypasses the HTML entirely, queries the backend API, and extracts thousands of courses in seconds.

---

## 5. Built-in Providers

Providers are custom "adapters" designed to defeat anti-scraping measures or extract data more efficiently than generic crawling.

### Aprende (`aprende.org`)
*   **Strategy**: API Interception. Bypasses HTML parsing and hits the backend JSON API directly.
*   **Performance**: Extremely fast. Requires no rendering.

### NetAcad (`netacad.com`)
*   **Strategy**: Dual-Mode.
    *   **Static (Default)**: Parses the `sitemap.xml` to construct course records from slugs. Bypasses 403 Forbidden blocks.
    *   **Rendered (`--render`)**: Uses Playwright to wait for the React SPA to hydrate.

---

## 6. Dynamic Data Schema

The scraper strictly adheres to the [Schema.org Course specification](https://schema.org/Course). 

Unlike typical Python projects where schemas are hardcoded, this scraper **dynamically generates** its `Course` validation model at runtime by parsing the full official Schema.org RDF vocabulary (`schemas/course_schema.rdf`). 

### Adding New Fields
If you need to extract a new metadata field, you **do not need to write Python code**. You only need to ensure the property exists in `schemas/course_schema.rdf`. The software automatically adapts, validates it, and adds a column for it in the CSV.

### Flattened Output for Omeka S
Systems like Omeka S require flat structures. The exporter (`csv_exporter.py`) automatically flattens complex objects. 
For example, `price` and `priceCurrency` (which technically belong to a nested `schema:offers` object) are mapped directly onto the `Course` root row.

### Key Export Columns
Over 140 properties are supported. The most common are:
*   `schema:name`: Course Title
*   `schema:description`: Course synopsis
*   `schema:url`: Permalink
*   `schema:provider`: Organization offering the course
*   `schema:keywords`: Comma-separated tags
*   `schema:timeRequired`: ISO 8601 duration (e.g., `PT6H`)
*   `schema:price`: Cost of the course

---

## 7. Developer Guide: Adding a New Provider

If you encounter a site that the generic crawler cannot handle, you can build a Provider.

1.  Create a new file in `providers/` (e.g., `providers/my_site.py`).
2.  Inherit from `ProviderBase`.
3.  Implement `can_handle()` and `scrape()`.

**Template:**
```python
import urllib.parse
from typing import Iterator
from .base import ProviderBase
from schemas.models import Course

class MySiteProvider(ProviderBase):
    provider_name = "MySite"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        # Detect if this URL belongs to your site
        return "mysite.com" in urllib.parse.urlparse(url).netloc

    def scrape(self, url: str, render: bool = False) -> Iterator[Course]:
        # 1. Fetch the data (use self.crawler.get(url) or httpx)
        # 2. Parse the data
        # 3. Yield Course objects
        
        yield Course(
            name="Advanced Python",
            url=url,
            price=99.99
        )
```
The architecture auto-discovers your file. Next time you run `cli.py` with a `mysite.com` URL, your custom logic will execute automatically!
