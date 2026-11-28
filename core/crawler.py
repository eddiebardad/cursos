"""HTTP and browser clients with courtesy delays and bounded BFS crawling."""

from __future__ import annotations

import collections
import ipaddress
import socket
import time
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

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
from core.exceptions import (
    HTTPStatusError,
    NetworkError,
    ScraperException,
    UpstreamFormatError,
    WAFChallengeError,
)
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

WaitUntil = Literal["commit", "domcontentloaded", "load"]
ExpectedFormat = Literal["json", "xml", "html"]
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
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
MAX_REQUEST_DURATION_SECONDS = 240.0
MAX_RETRIES = 2
_MAX_REDIRECTS = 10
_LOGIN_SEGMENTS = {"login", "signin", "auth"}


class Crawler:
    def __init__(self, render: bool = False) -> None:
        self.headers = {"User-Agent": config.USER_AGENT}
        self.timeout = min(max(config.HTTP_TIMEOUT, 0.1), 25.0)
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
                follow_redirects=False,
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

    def _wait_for_courtesy_delay(self, deadline: float | None = None) -> None:
        if self._last_request_time > 0 and self.delay > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.delay:
                delay = self.delay - elapsed
                if deadline is not None:
                    delay = min(delay, max(0.0, deadline - time.monotonic()))
                time.sleep(delay)
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
        allowed_hosts: Collection[str] | None = None,
        reject_login_path: bool = False,
    ) -> Iterator[Page]:
        self.validate_safe_url(url, allowed_hosts, reject_login_path)
        self._wait_for_courtesy_delay()
        context = self._ensure_browser_context()
        page = context.new_page()
        blocked_requests: list[str] = []

        def guard_route(route: Any) -> None:
            request = route.request
            request_url = request.url
            try:
                main_navigation = (
                    request.is_navigation_request() and request.frame == page.main_frame
                )
                self.validate_safe_url(
                    request_url,
                    allowed_hosts if main_navigation else None,
                    reject_login_path and main_navigation,
                )
            except NetworkError:
                blocked_requests.append(request_url)
                route.abort()
            except PlaywrightError:
                route.abort()
            else:
                route.continue_()

        try:
            page.route("**/*", guard_route)
            try:
                response = page.goto(
                    url,
                    timeout=int(self.timeout * 1000),
                    wait_until=wait_until,
                )
            except PlaywrightError as exc:
                if blocked_requests:
                    raise NetworkError(
                        f"Browser navigation blocked unsafe URL: {blocked_requests[-1]}"
                    ) from exc
                raise
            final_url = page.url if isinstance(page.url, str) else url
            self.validate_safe_url(final_url, allowed_hosts, reject_login_path)
            status = getattr(response, "status", None)
            if response is not None and isinstance(status, int) and status >= 400:
                challenged = (
                    status == 403
                    or response.headers.get("cf-mitigated", "").casefold() == "challenge"
                )
                raise HTTPStatusError(
                    status,
                    final_url,
                    waf_blocked=challenged,
                )
            page_html = page.content()
            if "just a moment" in page_html[:4096].casefold() or "cf-mitigated" in page_html[:4096].casefold():
                raise WAFChallengeError(final_url)
            yield page
        finally:
            page.close()

    def get(
        self,
        url: str,
        render: bool | None = None,
        headers: dict[str, str] | None = None,
        expected_format: ExpectedFormat | None = None,
        retries: int = 1,
        max_bytes: int = MAX_RESPONSE_BYTES,
        allowed_hosts: Collection[str] | None = None,
        reject_login_path: bool = False,
        **kwargs: Any,
    ) -> str:
        use_render = self.render if render is None else render
        if use_render:
            with self.open_page(
                url,
                allowed_hosts=allowed_hosts,
                reject_login_path=reject_login_path,
            ) as page:
                body = page.content()
                if len(body.encode("utf-8")) > max_bytes:
                    raise UpstreamFormatError(
                        f"Response exceeded the {max_bytes}-byte limit from {page.url}"
                    )
                return body

        return self._get_http_response(
            url,
            headers,
            expected_format=expected_format,
            retries=retries,
            max_bytes=max_bytes,
            allowed_hosts=allowed_hosts,
            reject_login_path=reject_login_path,
            **kwargs,
        ).text

    def get_bytes(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        expected_format: ExpectedFormat | None = None,
        retries: int = 1,
        max_bytes: int = MAX_RESPONSE_BYTES,
        allowed_hosts: Collection[str] | None = None,
        reject_login_path: bool = False,
        **kwargs: Any,
    ) -> bytes:
        """Fetch response bytes using the shared HTTP client and request policy."""
        return self._get_http_response(
            url,
            headers,
            expected_format=expected_format,
            retries=retries,
            max_bytes=max_bytes,
            allowed_hosts=allowed_hosts,
            reject_login_path=reject_login_path,
            **kwargs,
        ).content

    def _get_http_response(
        self,
        url: str,
        headers: dict[str, str] | None,
        expected_format: ExpectedFormat | None = None,
        retries: int = 1,
        max_bytes: int = MAX_RESPONSE_BYTES,
        allowed_hosts: Collection[str] | None = None,
        reject_login_path: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        merged_headers = {**self.headers, **(headers or {})}
        attempt_limit = min(max(0, retries), MAX_RETRIES)
        deadline = time.monotonic() + MAX_REQUEST_DURATION_SECONDS
        for attempt in range(attempt_limit + 1):
            if time.monotonic() >= deadline:
                raise NetworkError(f"Request exceeded its time budget for {url}")
            request_url = url
            try:
                if self._client is None:
                    with httpx.Client(
                        headers=merged_headers,
                        timeout=self.timeout,
                        follow_redirects=False,
                    ) as client:
                        response = self._request_limited(
                            client,
                            request_url,
                            merged_headers,
                            max_bytes,
                            allowed_hosts,
                            reject_login_path,
                            kwargs,
                            deadline,
                        )
                else:
                    response = self._request_limited(
                        self._client,
                        request_url,
                        merged_headers,
                        max_bytes,
                        allowed_hosts,
                        reject_login_path,
                        kwargs,
                        deadline,
                    )
            except httpx.RequestError as exc:
                if time.monotonic() >= deadline:
                    raise NetworkError(f"Request exceeded its time budget for {url}") from exc
                if attempt < attempt_limit:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise NetworkError(f"Request failed for {url}: {exc}") from exc

            challenge = ResponseGuard.is_waf_challenge(response)
            retryable = response.status_code == 429 or 500 <= response.status_code <= 599
            if retryable and not challenge and attempt < attempt_limit:
                time.sleep(0.25 * (2**attempt))
                continue
            ResponseGuard.validate(response, expected_format=expected_format)
            return response

        raise NetworkError(f"Request failed for {url}")

    def _request_limited(
        self,
        client: httpx.Client,
        url: str,
        headers: dict[str, str],
        max_bytes: int,
        allowed_hosts: Collection[str] | None,
        reject_login_path: bool,
        kwargs: dict[str, Any],
        deadline: float,
    ) -> httpx.Response:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")

        current_url = url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NetworkError(f"Request exceeded its time budget for {url}")
            self.validate_safe_url(current_url, allowed_hosts, reject_login_path)
            self._wait_for_courtesy_delay(deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NetworkError(f"Request exceeded its time budget for {url}")
            request_kwargs = {**kwargs, "timeout": min(self.timeout, remaining)}
            with client.stream(
                "GET",
                current_url,
                headers=headers,
                follow_redirects=False,
                **request_kwargs,
            ) as response:
                self.validate_safe_url(
                    str(response.url),
                    allowed_hosts,
                    reject_login_path,
                )
                if response.status_code in {301, 302, 303, 307, 308} and config.FOLLOW_REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        break
                    if redirect_count == _MAX_REDIRECTS:
                        raise NetworkError(f"Too many redirects while requesting {url}")
                    current_url = urljoin(str(response.url), location)
                    self.validate_safe_url(current_url, allowed_hosts, reject_login_path)
                    continue

                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > max_bytes:
                            raise UpstreamFormatError(
                                f"Response exceeded the {max_bytes}-byte limit from {response.url}"
                            )
                    except ValueError as exc:
                        raise UpstreamFormatError(
                            f"Invalid Content-Length from {response.url}"
                        ) from exc

                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=min(8192, max_bytes + 1)):
                    if len(content) + len(chunk) > max_bytes:
                        raise UpstreamFormatError(
                            f"Response exceeded the {max_bytes}-byte limit from {response.url}"
                        )
                    content.extend(chunk)
                response_headers = dict(response.headers)
                response_headers.pop("content-encoding", None)
                response_headers["content-length"] = str(len(content))
                return httpx.Response(
                    status_code=response.status_code,
                    headers=response_headers,
                    content=bytes(content),
                    request=response.request,
                )

        raise NetworkError(f"Could not follow redirect while requesting {url}")

    @staticmethod
    def validate_safe_url(
        url: str,
        allowed_hosts: Collection[str] | None = None,
        reject_login_path: bool = False,
    ) -> None:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").casefold().rstrip(".")
            port = parsed.port
        except ValueError as exc:
            raise NetworkError(f"Invalid URL: {url}") from exc

        if parsed.scheme.casefold() != "https" or not host:
            raise NetworkError(f"Only absolute HTTPS URLs are allowed: {url}")
        if parsed.username is not None or parsed.password is not None:
            raise NetworkError(f"Credentials in URLs are not allowed: {url}")
        if port not in {None, 443}:
            raise NetworkError(f"Non-standard HTTPS ports are not allowed: {url}")
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise NetworkError(f"Local destinations are not allowed: {url}")
        try:
            address = ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise NetworkError(f"Non-public IP destinations are not allowed: {url}")

        if allowed_hosts is not None:
            permitted = {entry.casefold().rstrip(".") for entry in allowed_hosts}
            if host not in permitted:
                raise NetworkError(f"URL host is not allowed: {host}")
        if address is None:
            try:
                addresses = socket.getaddrinfo(
                    host,
                    port or 443,
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                raise NetworkError(f"Could not resolve URL host: {host}") from exc
            for entry in addresses:
                resolved_host_value = entry[4][0]
                if not isinstance(resolved_host_value, str):
                    raise NetworkError(
                        f"Host resolution returned an invalid IP address: {host}"
                    )
                resolved_host = resolved_host_value.split("%", 1)[0]
                try:
                    resolved_address = ipaddress.ip_address(resolved_host)
                except ValueError as exc:
                    raise NetworkError(
                        f"Host resolution returned an invalid IP address: {host}"
                    ) from exc
                if not resolved_address.is_global:
                    raise NetworkError(
                        f"URL host resolves to a non-public IP address: {host}"
                    )
        if reject_login_path and any(
            segment.casefold() in _LOGIN_SEGMENTS
            for segment in parsed.path.split("/")
        ):
            raise NetworkError(f"Login URLs are not allowed: {url}")


class ResponseGuard:
    """Validate HTTP status and prevent HTML error pages from masquerading as data."""

    @staticmethod
    def is_waf_challenge(response: httpx.Response) -> bool:
        if response.headers.get("cf-mitigated", "").casefold() == "challenge":
            return True
        body = response.text[:4096].casefold()
        return "just a moment" in body or "cf-mitigated" in body

    @staticmethod
    def validate(
        response: httpx.Response,
        *,
        expected_format: ExpectedFormat | None = None,
    ) -> None:
        status = response.status_code
        challenge = ResponseGuard.is_waf_challenge(response)
        if challenge and status < 400:
            raise WAFChallengeError(str(response.url))
        if status >= 400 or 300 <= status < 400:
            raise HTTPStatusError(
                status,
                str(response.url),
                waf_blocked=status == 403 or challenge,
            )

        if expected_format not in {"json", "xml"}:
            return

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        body = response.content.lstrip().lower()
        html_body = (
            body.startswith(b"<!doctype html")
            or body.startswith(b"<html")
        )
        if content_type == "text/html" or html_body:
            raise UpstreamFormatError(
                f"Expected {expected_format.upper()} from {response.url}, received HTML"
            )


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
    start_host = urlsplit(start_url).hostname
    allowed_hosts = [start_host] if start_host else []

    with Crawler(render=render) as crawler:
        while queue and pages_crawled < max_pages:
            url = queue.popleft()
            try:
                logger.info("Crawling %s", url)
                html = crawler.get(
                    url,
                    render=render,
                    allowed_hosts=allowed_hosts,
                    reject_login_path=True,
                )
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
