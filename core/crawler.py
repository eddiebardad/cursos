import httpx
from config import config
from core.exceptions import NetworkError
import collections
from typing import Iterator, Tuple, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

class Crawler:
    def __init__(self):
        self.headers = {"User-Agent": config.USER_AGENT}
        self.timeout = config.HTTP_TIMEOUT

    def get(self, url: str, render: bool = False, headers: dict = None, **kwargs) -> str:
        if render:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, timeout=self.timeout * 1000, wait_until="networkidle")
                    # Give SPAs a little extra time to hydrate/render content
                    page.wait_for_timeout(3000)
                    html = page.content()
                    browser.close()
                    return html
            except ImportError:
                logger.error("Playwright is not installed. Please install it to use render=True. Falling back to static fetch.")
                pass

        # Merge instance default headers with any extra headers passed in
        merged_headers = {**self.headers, **(headers or {})}

        try:
            with httpx.Client(headers=merged_headers, timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, **kwargs)
                response.raise_for_status()
                return response.text
        except httpx.RequestError as e:
            raise NetworkError(f"Request failed for {url}: {e}")
        except httpx.HTTPStatusError as e:
            raise NetworkError(f"HTTP error {e.response.status_code} for {url}: {e}")

def crawl_site(start_url: str, provider=None, render: bool = False, max_pages: int = 100) -> Iterator[Tuple[str, str]]:
    """BFS traversal of a site."""
    from core.parser import Parser
    
    crawler = Crawler()
    queue = collections.deque([start_url])
    visited = set([start_url])
    pages_crawled = 0
    
    while queue and pages_crawled < max_pages:
        url = queue.popleft()
        
        try:
            logger.info(f"Crawling {url}")
            html = crawler.get(url, render=render)
            yield html, url
            pages_crawled += 1
            
            # Extract and enqueue links
            soup = Parser.parse_html(html)
            for link in Parser.extract_internal_links(soup, url):
                if link not in visited:
                    if provider is None or provider.should_crawl(link):
                        visited.add(link)
                        queue.append(link)
                        
        except NetworkError as e:
            logger.error(e)
