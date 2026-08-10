# Course Scraper

Welcome to the **Course Scraper**! This tool is a robust, scalable web scraping architecture designed to extract educational course metadata from various websites (like NetAcad, Aprende.org, and generic catalogs). 

It normalizes this diverse data into a flat, Schema.org-compliant CSV format, making it incredibly easy to import into content management systems like **Omeka S**.

> [!TIP]
> **New to the project?** Read the comprehensive [User Guide](file:///docs/user_guide.md) for an in-depth look at the architecture, how the CLI works, and how to add new scraping providers!

## Quick Start & Installation

Ensure you have **Python 3.9+** installed. We recommend using a modern Python manager like `uv`.

1. **Install Base Requirements:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Install Playwright Browsers (Optional but recommended):**
   If you plan to scrape JavaScript-heavy dynamic sites (SPAs), you must install the Playwright browser binaries:
   ```bash
   playwright install chromium
   ```

## Usage Examples

The scraper uses a unified CLI that automatically detects which site adapter to use based on the URL you provide. If it doesn't recognize the domain, it falls back to a powerful generic crawler that heuristically searches for Schema.org JSON-LD or OpenGraph metadata.

### 1. Generic Core on a Static Site
When you point the scraper to a generic site, it will spider the domain up to the specified `--max-pages` and attempt to parse any course pages it finds.
```bash
# Spider up to 50 pages on a generic site using fast, static HTTP requests
uv run python cli.py --url "https://example-university.edu/courses" --max-pages 50 --output generic_results.csv
```

### 2. Running the `aprende.org` Provider
The `aprende.org` adapter is specially designed to bypass HTML scraping and map their hidden API directly to our standard format.
```bash
# Provide a specific course URL; the adapter will intercept it and query the API
uv run python cli.py --url "https://aprende.org/pages.php?r=.m_curso&cursoID=123" --max-pages 1 --output aprende.csv
```

### 3. Running `netacad.com` (With and Without Render)
NetAcad can be scraped statically, but if the content is heavily dynamic, you can toggle the Playwright JavaScript engine on demand.

**Without Rendering (Fast, Static HTTP):**
```bash
uv run python cli.py --url "https://www.netacad.com/courses/all-courses" --max-pages 20
```

**With Rendering (Slower, Executes JavaScript):**
```bash
# Note: Requires `playwright install` to have been run!
uv run python cli.py --url "https://www.netacad.com/courses/all-courses" --max-pages 20 --render --output netacad_dynamic.csv
```

## 4. Standalone Windows Executable
The project can also be packaged as a single-file Windows executable that runs without opening a terminal window.

If you have already built the app, launch it directly from `dist/gui_app.exe`.

If you want to build it yourself from source, run this from the project root:
```bash
python -m PyInstaller gui_app.spec
```

The standalone app bundles:
* the scraper backend
* built-in providers like Aprende, NetAcad, Hubspot, and CognitiveClass
* the dynamic course schema (`schemas/course_schema.rdf`)
* the UI and logging support for packaged execution

### Executable UI Options
The GUI exposes the same core scraper functionality in a modern interface:
* **Starting URL**: The site or course page to scrape.
* **Provider**: Auto-detect or force a built-in adapter.
* **Max pages to crawl**: Limits how far the generic spider will search.
* **Render JavaScript with Playwright**: Enable browser rendering for SPAs.
* **Output file**: Save path for CSV or JSON-LD output.
* **Run Scrape**: Launch the scraping workflow.
* **Console output**: Live progress and log messages are shown inside the app.

The executable uses the same backend as the CLI, so provider detection, API-based adapters, and generic crawling all work the same way.

## Logging & Run Summaries

The CLI includes a built-in incremental logger. Every time a scrape finishes (successfully or with an error), a summary of the run is appended to `scraper_runs.log`. This file tracks:
- Run status (SUCCESS or FAILED)
- The URL and provider used
- The output file generated
- The total number of courses extracted
- Any error messages encountered

---

## Expected Output & Verification

The scraper outputs a flat CSV file (`results.csv` by default) mapped to the [Schema.org Course specification](https://schema.org/Course).

### Output File Structure
Your CSV will contain columns like:
*   `schema:name`: The course title.
*   `schema:description`: The course description (truncated/normalized).
*   `schema:url`: The direct link to the course.
*   `schema:provider`: The organization offering the course.
*   `schema:price` / `schema:priceCurrency`: Flattened from the `Offer` object.
*   `schema:keywords`: Extracted tags, joined into a comma-separated string (e.g., `"python, coding, web"`).

### How to Verify the Scraper Works
1. Run a targeted scrape using one of the examples above (e.g., the `aprende.org` example).
2. Open the resulting `.csv` file in Excel, Numbers, or via the terminal (`cat aprende.csv`).
3. Verify that the header row contains the exact `schema:` aliases.
4. Verify that the list fields (like keywords) are properly comma-separated and that nested objects (like price) are properly flattened into their respective columns.
5. You can now take this CSV and import it directly into **Omeka S** using the CSV Import module!
