"""
core/crawler.py
==============================================================================
Cliente de rastreo HTTP y navegación con soporte para pausas de cortesía.
==============================================================================
"""

import collections
import time
from collections.abc import Iterator

import httpx

from config import config
from core.exceptions import NetworkError
from utils.logger import get_logger

logger = get_logger(__name__)


class Crawler:
    def __init__(self) -> None:
        self.headers = {"User-Agent": config.USER_AGENT}
        self.timeout = config.HTTP_TIMEOUT
        self.delay = config.COURTESY_DELAY
        self._last_request_time: float = 0.0
        self._client: httpx.Client | None = None

    def __enter__(self) -> "Crawler":
        self._client = httpx.Client(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=config.FOLLOW_REDIRECTS,
        )
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def get(self, url: str, render: bool = False, headers: dict | None = None, **kwargs) -> str:
        if self._last_request_time > 0 and self.delay > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

        if render:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, timeout=int(self.timeout * 1000), wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    html = page.content()
                    browser.close()
                    return html
            except ImportError:
                logger.error(
                    "Playwright is not installed. Please install it to use render=True. "
                    "Falling back to static fetch."
                )

        merged_headers = {**self.headers, **(headers or {})}

        try:
            if self._client:
                response = self._client.get(url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.text

            with httpx.Client(
                headers=merged_headers,
                timeout=self.timeout,
                follow_redirects=config.FOLLOW_REDIRECTS,
            ) as client:
                response = client.get(url, **kwargs)
                response.raise_for_status()
                return response.text
        except httpx.RequestError as e:
            raise NetworkError(f"Request failed for {url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise NetworkError(f"HTTP error {e.response.status_code} for {url}: {e}") from e


def crawl_site(
    start_url: str,
    provider=None,
    render: bool = False,
    max_pages: int = 100,
) -> Iterator[tuple[str, str]]:
    """
    BFS traversal of a site.
    DESACTIVADO por defecto en cli.py — solo se invoca si --enable-bfs está activo.
    """
    from core.parser import Parser

    crawler = Crawler()
    queue = collections.deque([start_url])
    visited = {start_url}
    pages_crawled = 0

    while queue and pages_crawled < max_pages:
        url = queue.popleft()

        try:
            logger.info(f"Crawling {url}")
            html = crawler.get(url, render=render)
            yield html, url
            pages_crawled += 1

            soup = Parser.parse_html(html)
            for link in Parser.extract_internal_links(soup, url):
                if link not in visited:
                    if provider is None or provider.should_crawl(link):
                        visited.add(link)
                        queue.append(link)

        except NetworkError as e:
            logger.error(e)
