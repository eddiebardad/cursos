"""Reusable strategy drivers, including a generic sitemap/JSON-LD implementation."""

from __future__ import annotations

import gzip
import io
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from core.crawler import MAX_RESPONSE_BYTES, Crawler
from core.exceptions import NetworkError, UpstreamFormatError
from core.extractor import extract_course_candidates
from core.manifest import ProviderDefinition
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

Driver = Callable[
    [Any, str, ProviderDefinition, dict[str, Any], int, bool],
    list[Course],
]
_DRIVERS: dict[str, Driver] = {}


def register_driver(name: str) -> Callable[[Driver], Driver]:
    def decorator(driver: Driver) -> Driver:
        if name in _DRIVERS:
            raise ValueError(f"Driver already registered: {name}")
        _DRIVERS[name] = driver
        return driver

    return decorator


def available_drivers() -> tuple[str, ...]:
    return tuple(sorted(_DRIVERS))


def run_driver(
    name: str,
    provider_adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any] | None = None,
    limit: int = 0,
    enable_modules: bool = False,
) -> list[Course]:
    driver = _DRIVERS.get(name)
    if driver is None:
        raise ValueError(f"Unknown strategy driver: {name}")
    return driver(
        provider_adapter,
        url,
        provider,
        params or {},
        limit,
        enable_modules,
    )


def _adapter_scrape(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    del provider, params
    return list(
        adapter.scrape(
            url,
            limit=limit,
            enable_modules=enable_modules,
        )
    )


@register_driver("ms_learn_api")
def _ms_learn_api(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    return _adapter_scrape(adapter, url, provider, params, limit, enable_modules)


@register_driver("aprende_api")
def _aprende_api(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    return _adapter_scrape(adapter, url, provider, params, limit, enable_modules)


@register_driver("netacad_playwright")
def _netacad_playwright(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    return _adapter_scrape(adapter, url, provider, params, limit, enable_modules)


def _openlearn_strategy(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
    strategy: str,
) -> list[Course]:
    del provider, params, enable_modules
    return list(adapter.scrape_strategy(url, strategy=strategy, limit=limit))


@register_driver("openlearn_sitemap")
def _openlearn_sitemap(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    return _openlearn_strategy(
        adapter,
        url,
        provider,
        params,
        limit,
        enable_modules,
        "sitemap",
    )


@register_driver("openlearn_catalogue")
def _openlearn_catalogue(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    return _openlearn_strategy(
        adapter,
        url,
        provider,
        params,
        limit,
        enable_modules,
        "catalogue",
    )


class SitemapJsonLdDriver:
    """Fetch Course records from sitemap URLs and their JSON-LD pages."""

    def __init__(
        self,
        crawler: Crawler,
        provider: ProviderDefinition,
        params: dict[str, Any],
        limit: int = 0,
    ) -> None:
        sitemap_url = params.get("sitemap_url")
        if not isinstance(sitemap_url, str) or not sitemap_url.strip():
            raise ValueError("sitemap_jsonld requires params.sitemap_url")
        self.crawler = crawler
        self.provider = provider
        self.sitemap_url = sitemap_url
        self.url_pattern = params.get("url_pattern")
        self.limit = limit
        self._seen_sitemaps: set[str] = set()

    def scrape(self) -> list[Course]:
        course_urls = self._sitemap_urls(self.sitemap_url)
        courses: list[Course] = []
        for course_url in course_urls:
            html = self.crawler.get(
                course_url,
                expected_format="html",
                allowed_hosts=self.provider.allowed_hosts,
                reject_login_path=True,
                max_bytes=MAX_RESPONSE_BYTES,
            )
            for candidate in extract_course_candidates(html, course_url):
                values = dict(candidate)
                values.setdefault("provider", self.provider.name)
                values.setdefault("in_language", self.provider.default_language)
                try:
                    courses.append(Course(**values))
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "sitemap_jsonld skipped invalid Course at %s: %s",
                        course_url,
                        exc,
                    )
                if self.limit > 0 and len(courses) >= self.limit:
                    return courses
        return courses

    def _sitemap_urls(self, sitemap_url: str, depth: int = 0) -> list[str]:
        if not self._allowed_sitemap_url(sitemap_url):
            raise UpstreamFormatError(f"Untrusted sitemap URL: {sitemap_url}")
        sitemap_url = self._normalize_sitemap_url(sitemap_url)
        if sitemap_url in self._seen_sitemaps:
            return []
        if depth >= 10 or len(self._seen_sitemaps) >= 100:
            raise UpstreamFormatError("Sitemap index exceeded recursion or document limits")
        self._seen_sitemaps.add(sitemap_url)
        payload = self.crawler.get_bytes(
            sitemap_url,
            expected_format="xml",
            allowed_hosts=self.provider.allowed_hosts,
            max_bytes=MAX_RESPONSE_BYTES,
        )
        if payload.startswith(b"\x1f\x8b"):
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
                    payload = compressed.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise UpstreamFormatError(
                        f"Decompressed sitemap exceeded {MAX_RESPONSE_BYTES} bytes"
                    )
            except (OSError, EOFError) as exc:
                raise UpstreamFormatError(f"Invalid compressed sitemap {sitemap_url}: {exc}") from exc
        try:
            root = ET.fromstring(payload)
        except (ET.ParseError, DefusedXmlException) as exc:
            raise UpstreamFormatError(f"Invalid sitemap XML from {sitemap_url}: {exc}") from exc

        root_name = root.tag.rsplit("}", 1)[-1].casefold()
        locations = [
            (element.text or "").strip()
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].casefold() == "loc" and element.text
        ]
        if root_name == "sitemapindex":
            result: list[str] = []
            for child_sitemap in locations:
                if not self._allowed_sitemap_url(child_sitemap):
                    logger.warning(
                        "sitemap_jsonld skipped untrusted nested sitemap: %s",
                        child_sitemap,
                    )
                    continue
                result.extend(self._sitemap_urls(child_sitemap, depth + 1))
            return result
        if root_name != "urlset":
            raise UpstreamFormatError(
                f"Expected urlset or sitemapindex from {sitemap_url}, got {root_name!r}"
            )

        pattern: re.Pattern[str] | None = None
        if self.url_pattern is not None:
            if not isinstance(self.url_pattern, str):
                raise ValueError("url_pattern must be a string")
            try:
                pattern = re.compile(self.url_pattern)
            except re.error as exc:
                raise ValueError(f"Invalid sitemap url_pattern: {exc}") from exc

        return [
            location
            for location in locations
            if self._allowed_course_url(location)
            and (pattern is None or pattern.search(location))
        ]

    def _allowed_course_url(self, url: str) -> bool:
        try:
            Crawler.validate_safe_url(
                url,
                self.provider.allowed_hosts,
                reject_login_path=True,
            )
        except NetworkError:
            return False
        parsed = urlsplit(url)
        return bool(parsed.path and parsed.path != "/")

    def _allowed_sitemap_url(self, url: str) -> bool:
        try:
            Crawler.validate_safe_url(url, self.provider.allowed_hosts)
        except NetworkError:
            return False
        path = urlsplit(url).path.casefold()
        return path.endswith(".xml") or path.endswith(".xml.gz")

    @staticmethod
    def _normalize_sitemap_url(url: str) -> str:
        parsed = urlsplit(url)
        return parsed._replace(
            scheme=parsed.scheme.casefold(),
            netloc=(parsed.hostname or "").casefold().rstrip("."),
            fragment="",
        ).geturl()


@register_driver("sitemap_jsonld")
def _sitemap_jsonld(
    adapter: Any,
    url: str,
    provider: ProviderDefinition,
    params: dict[str, Any],
    limit: int,
    enable_modules: bool,
) -> list[Course]:
    del adapter, url, enable_modules
    with Crawler() as crawler:
        return SitemapJsonLdDriver(crawler, provider, params, limit).scrape()
