import typer
from typing_extensions import Annotated
from typing import Optional
from providers import get_provider_for_url, get_provider_by_name
from exporters.csv_exporter import CSVExporter
from exporters.jsonld_exporter import JSONLDExporter
from utils.logger import get_logger, log_run_summary
from core.crawler import crawl_site
from core.parser import parse_course_page

logger = get_logger(__name__)

app = typer.Typer(help="Course Scraper CLI")

def _execute_scrape(url: str, provider: Optional[str], max_pages: int, render: bool, output: str):
    provider_instance = None
    
    if provider:
        provider_instance = get_provider_by_name(provider)
        if not provider_instance:
            logger.error(f"Could not find a provider adapter named '{provider}'.")
            raise typer.Exit(code=1)
        logger.info(f"Forced provider adapter: {provider_instance.provider_name}")
    else:
        provider_instance = get_provider_for_url(url)
        if provider_instance:
            logger.info(f"Auto-detected provider: {provider_instance.provider_name}")
        else:
            if "aprende.org" in url:
                provider_instance = get_provider_by_name("Aprende")
                logger.info("Aprende URL detected; using Aprende provider adapter.")
            else:
                logger.info("No specific provider detected from URL, falling back to generic crawler.")

    if render:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Browser rendering is required (--render) but Playwright is unavailable. "
                "Please run: pip install playwright && playwright install"
            )
            raise typer.Exit(code=1)

    if output.endswith('.json'):
        exporter = JSONLDExporter()
    else:
        exporter = CSVExporter()
        
    logger.info(f"Starting spider at {url} (max {max_pages} pages)")
    
    courses = []
    error_msg = None
    try:
        if provider_instance:
            # Provider detected: always use its scrape() which knows the site's structure
            logger.info(f"Using {provider_instance.provider_name} adapter to scrape.")
            for course in provider_instance.scrape(url, render=render):
                courses.append(course)
                if max_pages and len(courses) >= max_pages * 10:
                    # Soft cap to avoid runaway scrapes (10 courses per page est.)
                    break
        else:
            # No provider: use generic BFS crawler
            for html, current_url in crawl_site(url, provider=None, render=render, max_pages=max_pages):
                course = parse_course_page(html, current_url)
                if course:
                    courses.append(course)

        if not courses:
            logger.warning("No course records were found on the specified URL(s).")
        else:
            exporter.export(courses, output)
            logger.info(f"Scraping completed successfully. Extracted {len(courses)} courses to {output}.")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Scraping failed: {e}", exc_info=True)
    finally:
        # Write to incremental summary log
        prov_name = provider_instance.provider_name if provider_instance else None
        log_run_summary(url, output, prov_name, render, len(courses), error_msg)
        
    if error_msg:
        raise typer.Exit(code=1)

@app.command("run")
def run_command(
    url: Annotated[str, typer.Option(help="Starting URL to crawl or scrape")],
    provider: Annotated[Optional[str], typer.Option(help="Force a specific adapter by name")] = None,
    max_pages: Annotated[int, typer.Option(help="Maximum number of pages to spider")] = 100,
    render: Annotated[bool, typer.Option(help="Use Playwright to render JavaScript")] = False,
    output: Annotated[str, typer.Option(help="Output file path")] = "results.csv"
):
    """Scrape course information from a URL."""
    _execute_scrape(url, provider, max_pages, render, output)

@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    url: Annotated[Optional[str], typer.Option(help="Starting URL to crawl or scrape")] = None,
    provider: Annotated[Optional[str], typer.Option(help="Force a specific adapter by name")] = None,
    max_pages: Annotated[int, typer.Option(help="Maximum number of pages to spider")] = 100,
    render: Annotated[bool, typer.Option(help="Use Playwright to render JavaScript")] = False,
    output: Annotated[str, typer.Option(help="Output file path")] = "results.csv"
):
    """Course Scraper CLI entry point."""
    if ctx.invoked_subcommand is None:
        if url:
            _execute_scrape(url, provider, max_pages, render, output)
        else:
            print(ctx.get_help())

def main():
    app()

if __name__ == "__main__":
    main()
