import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import ClassVar

from core.crawler import Crawler
from core.exceptions import NetworkError
from core.parser import parse_course_page
from schemas.models import AccessType, Course
from utils.logger import get_logger

from .base import ProviderBase

logger = get_logger(__name__)


class HubspotProvider(ProviderBase):
    provider_name = "HubSpot Academy"
    provider_aliases: ClassVar[tuple[str, ...]] = ("hubspot", "hubspotacademy")
    default_url = "https://academy.hubspot.com/es/courses"
    sitemap_url = "https://academy.hubspot.com/sitemap.xml"
    _course_defaults: ClassVar[dict[str, object]] = {
        "provider": "HubSpot Academy",
        "access_type": AccessType.free_with_certificate,
    }
    _excluded_slugs: ClassVar[set[str]] = {
        "category",
        "categories",
        "page",
        "pagination",
        "search",
        "tag",
        "tags",
        "topic",
        "topics",
    }

    @classmethod
    def can_handle(cls, url: str) -> bool:
        hostname = urllib.parse.urlsplit(url).hostname or ""
        return hostname.casefold() == "academy.hubspot.com"

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        logger.info("Scraping %s URL: %s", self.provider_name, url)
        if self._is_course_url(url):
            with Crawler() as crawler:
                html = crawler.get(url)
            course = parse_course_page(html, url, defaults=self._course_defaults_for_url(url))
            if course is not None:
                yield course
            return

        locale_prefix = self._requested_locale_prefix(url)
        sitemap_url = (
            url
            if urllib.parse.urlsplit(url).path.rstrip("/").endswith("sitemap.xml")
            else self.sitemap_url
        )
        visited_sitemaps: set[str] = set()
        seen_urls: set[str] = set()
        emitted = 0
        sitemap_has_courses = False

        with Crawler() as crawler:
            for candidate_url in self._iter_sitemap_course_urls(
                crawler,
                sitemap_url,
                locale_prefix,
                visited_sitemaps,
            ):
                sitemap_has_courses = True
                if candidate_url not in seen_urls:
                    seen_urls.add(candidate_url)
                    course = self._scrape_course(crawler, candidate_url)
                    if course is not None:
                        yield course
                        emitted += 1
                        if limit > 0 and emitted >= limit:
                            return

            if not sitemap_has_courses:
                catalog_url = self._catalog_url(url, locale_prefix)
                try:
                    catalog_html = crawler.get(catalog_url)
                except NetworkError as exc:
                    logger.warning("Could not load HubSpot catalog fallback %s: %s", catalog_url, exc)
                    return

                fallback_urls = self._course_urls_from_catalog(
                    catalog_html,
                    catalog_url,
                    locale_prefix,
                )
                if not fallback_urls:
                    logger.warning(
                        "No localized HubSpot course URLs found in the sitemap or catalog %s.",
                        catalog_url,
                    )

                for candidate_url in fallback_urls:
                    if candidate_url in seen_urls:
                        continue
                    seen_urls.add(candidate_url)
                    course = self._scrape_course(crawler, candidate_url)
                    if course is not None:
                        yield course
                        emitted += 1
                        if limit > 0 and emitted >= limit:
                            return

    @classmethod
    def _is_course_url(cls, url: str) -> bool:
        return cls._course_slug(url) is not None

    @classmethod
    def _course_slug(cls, url: str) -> str | None:
        path = urllib.parse.urlsplit(url).path.strip("/")
        segments = path.split("/")
        if len(segments) == 3 and re.fullmatch(
            r"[a-z]{2}(?:-[a-z]{2})?",
            segments[0],
            re.IGNORECASE,
        ):
            if segments[1].casefold() != "courses":
                return None
            slug = segments[2]
        elif len(segments) == 2 and segments[0].casefold() == "courses":
            slug = segments[1]
        else:
            return None

        slug_lower = slug.casefold()
        if slug_lower in cls._excluded_slugs or re.fullmatch(r"(?:page[-_]?|)\d+", slug_lower):
            return None
        return slug

    @staticmethod
    def _requested_locale_prefix(url: str) -> str:
        path = urllib.parse.urlsplit(url).path.strip("/")
        match = re.match(
            r"^([a-z]{2}(?:-[a-z]{2})?)/courses(?:/|$)",
            path,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).split("-", maxsplit=1)[0].casefold()
        if re.match(r"^courses(?:/|$)", path, flags=re.IGNORECASE):
            return ""
        return "es"

    @classmethod
    def _matches_locale(cls, url: str, locale_prefix: str) -> bool:
        slug = cls._course_slug(url)
        if slug is None:
            return False
        path_parts = urllib.parse.urlsplit(url).path.strip("/").split("/")
        if locale_prefix:
            return (
                len(path_parts) == 3
                and path_parts[0].split("-", maxsplit=1)[0].casefold()
                == locale_prefix.casefold()
                and path_parts[1].casefold() == "courses"
            )
        return len(path_parts) == 2 and path_parts[0].casefold() == "courses"

    @classmethod
    def _iter_sitemap_course_urls(
        cls,
        crawler: Crawler,
        sitemap_url: str,
        locale_prefix: str,
        visited_sitemaps: set[str],
    ) -> Iterator[str]:
        if sitemap_url in visited_sitemaps:
            return
        visited_sitemaps.add(sitemap_url)
        try:
            sitemap_xml = crawler.get(sitemap_url)
        except NetworkError as exc:
            logger.warning("Could not load HubSpot sitemap %s: %s", sitemap_url, exc)
            return

        try:
            root = ET.fromstring(sitemap_xml)
        except ET.ParseError as exc:
            logger.warning("Invalid HubSpot sitemap XML from %s: %s", sitemap_url, exc)
            return

        root_name = root.tag.rsplit("}", 1)[-1].casefold()
        locations = [
            (element.text or "").strip()
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].casefold() == "loc" and element.text
        ]
        if root_name == "sitemapindex":
            for child_sitemap in locations:
                if cls._is_hubspot_url(child_sitemap):
                    yield from cls._iter_sitemap_course_urls(
                        crawler,
                        child_sitemap,
                        locale_prefix,
                        visited_sitemaps,
                    )
            return

        if root_name != "urlset":
            logger.warning("Unexpected HubSpot sitemap root element %s", root_name)
            return
        for location in locations:
            if cls._is_hubspot_url(location) and cls._matches_locale(location, locale_prefix):
                yield location

    @staticmethod
    def _is_hubspot_url(url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        return parsed.scheme in {"http", "https"} and parsed.hostname == "academy.hubspot.com"

    @classmethod
    def _catalog_url(cls, input_url: str, locale_prefix: str) -> str:
        parsed = urllib.parse.urlsplit(input_url)
        if locale_prefix:
            path = f"/{locale_prefix}/courses"
        else:
            path = "/courses"
        return urllib.parse.urlunsplit(
            (parsed.scheme or "https", parsed.netloc or "academy.hubspot.com", path, "", "")
        )

    @classmethod
    def _course_defaults_for_url(cls, course_url: str) -> dict[str, object]:
        path = urllib.parse.urlsplit(course_url).path.strip("/")
        match = re.match(
            r"^([a-z]{2}(?:-[a-z]{2})?)/courses(?:/|$)",
            path,
            flags=re.IGNORECASE,
        )
        if match:
            language = match.group(1).split("-", maxsplit=1)[0].casefold()
        elif path.casefold().startswith("courses/"):
            language = "en"
        else:
            language = "es"
        return {**cls._course_defaults, "in_language": language}

    @classmethod
    def _course_urls_from_catalog(
        cls,
        html: str,
        catalog_url: str,
        locale_prefix: str,
    ) -> list[str]:
        from core.parser import Parser

        soup = Parser.parse_html(html)
        results: list[str] = []
        seen: set[str] = set()
        for link in Parser.extract_internal_links(soup, catalog_url):
            if cls._matches_locale(link, locale_prefix) and link not in seen:
                seen.add(link)
                results.append(link)
        return results

    def _scrape_course(self, crawler: Crawler, course_url: str) -> Course | None:
        try:
            html = crawler.get(course_url)
        except NetworkError as exc:
            logger.warning("Could not load HubSpot course %s: %s", course_url, exc)
            return None
        return parse_course_page(
            html,
            course_url,
            defaults=self._course_defaults_for_url(course_url),
        )
