"""HTTP and browser clients with courtesy delays and bounded BFS crawling."""

from __future__ import annotations

import collections
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError

from config import config
from core.exceptions import NetworkError, ScraperException
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
_NON_HTML_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".bmp",
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".json",
    ".xml",
    ".rss",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".mp4",
    ".mp3",
    ".wav",
    ".avi",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".csv",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
}


class Crawler:
    def __init__(self, render: bool = False) -> None:
        self.headers = {"User-Agent": config.USER_AGENT}
        self.timeout = config.HTTP_TIMEOUT
        self.delay = config.COURTESY_DELAY
        self.render = render
        self._last_request_time: float = 0.0
        self._client: httpx.Client | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_context: BrowserContext | None = None

    def __enter__(self) -> Crawler:
        if self._client is None:
            self._client = httpx.Client(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=config.FOLLOW_REDIRECTS,
            )
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def close(self) -> None:
        context = self._browser_context
        browser = self._browser
        playwright = self._playwright
        client = self._client
        self._browser_context = None
        self._browser = None
        self._playwright = None
        self._client = None

        for resource, close_method in (
            (context, "close"),
            (browser, "close"),
            (playwright, "stop"),
            (client, "close"),
        ):
            if resource is None:
                continue
            try:
                getattr(resource, close_method)()
            except Exception as exc:
                logger.warning("Failed to close crawler resource %s: %s", close_method, exc)

    def _wait_for_courtesy_delay(self) -> None:
        if self._last_request_time > 0 and self.delay > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        self._last_request_time = time.monotonic()

    def _ensure_browser_context(self) -> BrowserContext:
        if self._browser_context is not None:
            return self._browser_context
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._browser_context = self._browser.new_context(user_agent=config.USER_AGENT)
        except PlaywrightError as exc:
            self.close()
            raise ScraperException(
                "Could not start Chromium. Install the Playwright browser with "
                "'uv run playwright install chromium'."
            ) from exc
        return self._browser_context

    @contextmanager
    def open_page(
        self,
        url: str,
        wait_until: WaitUntil = "domcontentloaded",
    ) -> Iterator[Page]:
        self._wait_for_courtesy_delay()
        context = self._ensure_browser_context()
        page = context.new_page()
        try:
            page.goto(
                url,
                timeout=int(self.timeout * 1000),
                wait_until=wait_until,
            )
            yield page
        finally:
            page.close()

    def get(
        self,
        url: str,
        render: bool | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> str:
        use_render = self.render if render is None else render
        if use_render:
            with self.open_page(url) as page:
                return page.content()

        self._wait_for_courtesy_delay()
        merged_headers = {**self.headers, **(headers or {})}
        try:
            if self._client is not None:
                response = self._client.get(url, headers=merged_headers, **kwargs)
            else:
                with httpx.Client(
                    headers=merged_headers,
                    timeout=self.timeout,
                    follow_redirects=config.FOLLOW_REDIRECTS,
                ) as client:
                    response = client.get(url, **kwargs)
            response.raise_for_status()
            return response.text
        except httpx.RequestError as exc:
            raise NetworkError(f"Request failed for {url}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise NetworkError(f"HTTP error {exc.response.status_code} for {url}: {exc}") from exc


def _is_non_html_asset(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return any(path.endswith(extension) for extension in _NON_HTML_EXTENSIONS)


def crawl_site(
    start_url: str,
    max_pages: int = 100,
    render: bool = False,
    limit: int = 0,
) -> list[Course]:
    """Crawl a site breadth-first, accepting only structured Course records."""
    from core.parser import Parser, parse_course_page

    queue = collections.deque([start_url])
    visited = {start_url}
    courses: list[Course] = []
    pages_crawled = 0

    with Crawler(render=render) as crawler:
        while queue and pages_crawled < max_pages:
            url = queue.popleft()
            try:
                logger.info("Crawling %s", url)
                html = crawler.get(url, render=render)
            except NetworkError as exc:
                logger.error("%s", exc)
                continue

            pages_crawled += 1
            course = parse_course_page(html, url, allow_dom_fallback=False)
            if course is not None:
                courses.append(course)
                if limit > 0 and len(courses) >= limit:
                    break

            soup = Parser.parse_html(html)
            for link in Parser.extract_internal_links(soup, url):
                if link in visited or _is_non_html_asset(link):
                    continue
                visited.add(link)
                queue.append(link)
    return courses
