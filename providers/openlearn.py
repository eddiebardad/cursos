"""OpenLearn free-course catalog provider."""

from __future__ import annotations

import gzip
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import Any, ClassVar

from bs4 import BeautifulSoup
from pydantic import ValidationError

from core.crawler import Crawler
from core.exceptions import NetworkError, ParsingError
from core.extractor import extract_course_candidates, extract_open_graph_metadata
from schemas.models import AccessType, Course
from utils.logger import get_logger

from .base import ProviderBase

logger = get_logger(__name__)


class OpenLearnProvider(ProviderBase):
    provider_name = "OpenLearn (The Open University)"
    provider_aliases: ClassVar[tuple[str, ...]] = ("openlearn", "open_learn", "OpenLearn")
    default_url = "https://www.open.edu/openlearn/free-courses/full-catalogue"
    course_sitemap_url = (
        "https://www.open.edu/openlearn/pluginfile.php/1/local_ocwsitemap/"
        "sitemap/0/courses_sitemap.xml.gz"
    )
    sitemap_index_url = (
        "https://www.open.edu/openlearn/pluginfile.php/1/local_ocwsitemap/"
        "sitemap/0/sitemap.xml"
    )
    _reserved_segments: ClassVar[set[str]] = {
        "about-openlearn",
        "badged-courses",
        "free-courses",
        "local",
        "podcasts",
        "profiles",
        "search-results",
        "subject-information",
        "study-skills",
        "work-skills",
    }

    @classmethod
    def can_handle(cls, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        hostname = (parsed.hostname or "").casefold()
        return hostname in {"open.edu", "www.open.edu"} and (
            parsed.path == "/openlearn" or parsed.path.startswith("/openlearn/")
        )

    @classmethod
    def _is_course_url(cls, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        if not cls.can_handle(url) or parsed.path.lower().endswith((".xml", ".xml.gz")):
            return False

        path = re.sub(r"/content-section-[^/]+/?$", "", parsed.path.rstrip("/"))
        parts = path.strip("/").split("/")
        if len(parts) < 3 or parts[0].casefold() != "openlearn":
            return False
        if any(part.casefold() in cls._reserved_segments for part in parts[1:]):
            return False
        return not any(part.casefold().startswith("content-section-") for part in parts)

    @staticmethod
    def _parse_sitemap_xml(payload: bytes) -> ET.Element:
        if payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        try:
            return ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ParsingError(f"OpenLearn returned invalid sitemap XML: {exc}") from exc

    @staticmethod
    def _locations(root: ET.Element) -> list[str]:
        return [
            (element.text or "").strip()
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].casefold() == "loc" and element.text
        ]

    @classmethod
    def _course_urls_from_sitemap(
        cls,
        crawler: Crawler,
        sitemap_url: str,
    ) -> list[str]:
        root = cls._parse_sitemap_xml(crawler.get_bytes(sitemap_url))
        root_name = root.tag.rsplit("}", 1)[-1].casefold()

        if root_name == "sitemapindex":
            course_sitemap = next(
                (
                    location
                    for location in cls._locations(root)
                    if "courses_sitemap" in urllib.parse.urlsplit(location).path.casefold()
                    and cls.can_handle(location)
                ),
                None,
            )
            if course_sitemap is None:
                return []
            root = cls._parse_sitemap_xml(crawler.get_bytes(course_sitemap))
            root_name = root.tag.rsplit("}", 1)[-1].casefold()

        if root_name != "urlset":
            raise ParsingError(f"Unexpected OpenLearn sitemap root element: {root_name}")

        urls: list[str] = []
        seen: set[str] = set()
        for location in cls._locations(root):
            parsed = urllib.parse.urlsplit(location)
            clean_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, "", "")
            )
            if cls._is_course_url(clean_url) and clean_url not in seen:
                seen.add(clean_url)
                urls.append(clean_url)
        return urls

    @classmethod
    def _sitemap_course_urls(
        cls,
        crawler: Crawler,
        requested_url: str,
    ) -> list[str]:
        requested_path = urllib.parse.urlsplit(requested_url).path.casefold()
        sitemap_urls = (
            [requested_url]
            if requested_path.endswith((".xml", ".xml.gz"))
            else [cls.course_sitemap_url, cls.sitemap_index_url]
        )
        for sitemap_url in sitemap_urls:
            try:
                course_urls = cls._course_urls_from_sitemap(crawler, sitemap_url)
            except (NetworkError, ParsingError, OSError, EOFError) as exc:
                logger.warning("Could not read OpenLearn sitemap %s: %s", sitemap_url, exc)
                continue
            if course_urls:
                return course_urls
        return []

    @classmethod
    def _catalog_course_urls(cls, html: str, catalog_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(catalog_url, str(anchor["href"]))
            parsed = urllib.parse.urlsplit(href)
            path = re.sub(r"/content-section-[^/]+/?$", "", parsed.path.rstrip("/"))
            clean_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, path, "", "")
            )
            if cls._is_course_url(clean_url) and clean_url not in seen:
                seen.add(clean_url)
                urls.append(clean_url)
        return urls

    @staticmethod
    def _catalog_page_url(catalog_url: str, page_number: int) -> str:
        parsed = urllib.parse.urlsplit(catalog_url)
        query = urllib.parse.urlencode({"page": page_number})
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, query, "")
        )

    @staticmethod
    def _text_from_meta(soup: BeautifulSoup, property_name: str) -> str | None:
        meta = soup.find("meta", attrs={"property": property_name})
        if meta is None:
            meta = soup.find("meta", attrs={"name": property_name})
        if meta is None:
            return None
        content = meta.get("content")
        return str(content).strip() if content else None

    @classmethod
    def _subject_signal(
        cls,
        soup: BeautifulSoup,
        url: str,
        title: str,
    ) -> str | None:
        breadcrumb = soup.find(
            "nav",
            attrs={"aria-label": re.compile("breadcrumb", re.IGNORECASE)},
        )
        if breadcrumb:
            parts = [
                part.strip()
                for part in re.split(
                    r"\s*[>›]\s*",
                    breadcrumb.get_text(" > ", strip=True),
                )
                if part.strip()
            ]
            if parts and parts[0].casefold() == "subjects":
                subject = next(
                    (
                        part
                        for part in parts[1:]
                        if part.casefold() not in {"free courses", title.casefold()}
                    ),
                    None,
                )
                if subject:
                    return subject

        parts = urllib.parse.urlsplit(url).path.strip("/").split("/")
        if len(parts) >= 3:
            return parts[1].replace("-", " ")
        return None

    @staticmethod
    def _time_required(text: str) -> str | None:
        match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(hours?|hrs?)\b",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return f"{match.group(1).replace(',', '.')} {match.group(2)}"

    @staticmethod
    def _educational_level(text: str) -> str | None:
        match = re.search(
            r"\bLevel\s*[123]\s*:\s*(Introductory|Intermediate|Advanced)\b",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).title() if match else None

    @staticmethod
    def _access_type(text: str) -> AccessType:
        if re.search(
            r"free statement of participation|free digital badge",
            text,
            flags=re.IGNORECASE,
        ):
            return AccessType.free_with_certificate
        return AccessType.free_no_certificate

    @classmethod
    def _course_from_page(cls, html: str, page_url: str) -> Course | None:
        candidates = extract_course_candidates(html, page_url)
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        access_type = cls._access_type(page_text)

        if candidates:
            for candidate in candidates:
                course_values = dict(candidate)
                course_values["provider"] = "OpenLearn (The Open University)"
                course_values["access_type"] = access_type
                course_values.setdefault("is_accessible_for_free", True)
                try:
                    return Course(**course_values)
                except (ValidationError, ValueError) as exc:
                    logger.info("OpenLearn Course metadata rejected for %s: %s", page_url, exc)
            return None

        if not cls._is_course_url(page_url):
            return None

        heading = soup.find("h1")
        if heading is None:
            return None
        heading_text = heading.get_text(" ", strip=True)
        if not heading_text:
            return None

        open_graph = extract_open_graph_metadata(html, page_url)
        title = open_graph.get("og:title") or heading_text
        description = (
            open_graph.get("og:description")
            or cls._text_from_meta(soup, "og:description")
            or cls._text_from_meta(soup, "description")
        )
        if not description:
            main_content = soup.find(["main", "article"]) or soup.body or soup
            description = next(
                (
                    paragraph.get_text(" ", strip=True)
                    for paragraph in main_content.find_all("p")
                    if len(paragraph.get_text(" ", strip=True)) >= 30
                ),
                None,
            )

        html_element = soup.find("html")
        language = html_element.get("lang") if html_element else None
        if not language:
            language = open_graph.get("og:locale")
        subject = cls._subject_signal(soup, page_url, str(title))
        image = open_graph.get("og:image") or cls._text_from_meta(soup, "og:image")
        values: dict[str, Any] = {
            "name": title,
            "url": page_url,
            "description": description,
            "provider": "OpenLearn (The Open University)",
            "in_language": language,
            "time_required": cls._time_required(page_text),
            "educational_level": cls._educational_level(page_text),
            "category": subject,
            "keywords": [subject] if subject else None,
            "access_type": access_type,
            "is_accessible_for_free": True,
            "image": image,
        }
        try:
            return Course(**values)
        except (ValidationError, ValueError) as exc:
            logger.info("OpenLearn DOM metadata rejected for %s: %s", page_url, exc)
            return None

    @classmethod
    def _iter_catalog_urls(
        cls,
        crawler: Crawler,
        catalog_url: str,
    ) -> Iterator[str]:
        seen: set[str] = set()
        for page_number in range(100):
            page_url = cls._catalog_page_url(catalog_url, page_number)
            html = crawler.get(page_url)
            page_course_urls = cls._catalog_course_urls(html, page_url)
            new_urls = [url for url in page_course_urls if url not in seen]
            if not new_urls and page_number > 0:
                return
            seen.update(new_urls)
            yield from new_urls

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        with Crawler() as crawler:
            if self._is_course_url(url):
                html = crawler.get(url)
                course = self._course_from_page(html, url)
                if course is not None:
                    yield course
                return

            sitemap_urls = self._sitemap_course_urls(crawler, url)
            requested_path = urllib.parse.urlsplit(url).path.casefold()
            catalog_url = (
                self.default_url
                if requested_path.endswith((".xml", ".xml.gz"))
                else url
            )
            course_urls = (
                iter(sitemap_urls)
                if sitemap_urls
                else self._iter_catalog_urls(crawler, catalog_url)
            )
            emitted = 0
            for course_url in course_urls:
                html = crawler.get(course_url)
                course = self._course_from_page(html, course_url)
                if course is None:
                    continue
                yield course
                emitted += 1
                if limit > 0 and emitted >= limit:
                    return
