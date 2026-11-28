"""Course-page parsing and safe DOM fallback."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup
from pydantic import ValidationError

from core.extractor import extract_course_candidates
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

_NON_COURSE_PATHS = {
    "about",
    "auth",
    "cart",
    "checkout",
    "contact",
    "cookies",
    "faq",
    "help",
    "legal",
    "login",
    "privacy",
    "register",
    "search",
    "signin",
    "signup",
    "terms",
}


class Parser:
    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                results.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                results.append(data)
        return results

    @staticmethod
    def extract_internal_links(soup: BeautifulSoup, base_url: str) -> list[str]:
        parsed_base = urllib.parse.urlsplit(base_url)
        base_domain = parsed_base.netloc.casefold()
        links: list[str] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).strip()
            parsed_href = urllib.parse.urlsplit(href)
            if parsed_href.scheme and parsed_href.scheme.casefold() not in {"http", "https"}:
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            parsed_url = urllib.parse.urlsplit(full_url)
            if parsed_url.scheme.casefold() not in {"http", "https"}:
                continue
            if parsed_url.netloc.casefold() != base_domain:
                continue

            clean_url = urllib.parse.urlunsplit(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.query,
                    "",
                )
            )
            if clean_url not in seen:
                seen.add(clean_url)
                links.append(clean_url)
        return links

    @staticmethod
    def detect_course_page(soup: BeautifulSoup) -> bool:
        return bool(
            extract_course_candidates(
                str(soup),
                "https://cursodex.invalid/course",
            )
        )

    @staticmethod
    def _blocked_fallback_path(url: str) -> bool:
        path = urllib.parse.urlsplit(url).path.strip("/")
        if not path:
            return True
        return any(segment.casefold() in _NON_COURSE_PATHS for segment in path.split("/"))

    @staticmethod
    def _meta_content(soup: BeautifulSoup, *, property_name: str, name: bool = False) -> str | None:
        attribute = "name" if name else "property"
        meta = soup.find("meta", attrs={attribute: property_name})
        if not meta:
            return None
        content = meta.get("content")
        return str(content).strip() if content else None

    @staticmethod
    def _parse_dom_fallback(html: str, url: str, defaults: dict[str, Any] | None) -> Course | None:
        if Parser._blocked_fallback_path(url):
            return None

        soup = Parser.parse_html(html)
        heading = soup.find("h1")
        if heading is None:
            return None
        title = heading.get_text(" ", strip=True)
        if not title:
            return None

        description_candidates = [
            Parser._meta_content(soup, property_name="og:description"),
            Parser._meta_content(soup, property_name="description", name=True),
        ]
        main_content = soup.find(["main", "article"]) or soup.body or soup
        description_candidates.extend(
            paragraph.get_text(" ", strip=True)
            for paragraph in main_content.find_all("p")
        )
        description = next(
            (
                candidate
                for candidate in description_candidates
                if candidate and len(candidate.strip()) >= 30
            ),
            None,
        )

        html_element = soup.find("html")
        language = html_element.get("lang") if html_element else None
        if not language:
            language = Parser._meta_content(soup, property_name="og:locale")
        image = Parser._meta_content(soup, property_name="og:image")

        values: dict[str, Any] = {
            "name": title,
            "url": url,
            "description": description,
            "in_language": language,
            "image": image,
            "review_notes": ["Extraído mediante fallback DOM sin metadatos estructurados Course"],
        }
        for key, value in (defaults or {}).items():
            if values.get(key) is None:
                values[key] = value
        try:
            return Course(**values)
        except ValidationError as exc:
            logger.info("DOM fallback did not produce a valid Course for %s: %s", url, exc)
            return None

    @staticmethod
    def parse_course_page(
        html: str,
        url: str,
        allow_dom_fallback: bool = True,
        defaults: dict[str, Any] | None = None,
    ) -> Course | None:
        candidates = extract_course_candidates(html, url)
        for candidate in candidates:
            values = dict(candidate)
            for key, value in (defaults or {}).items():
                if values.get(key) is None:
                    values[key] = value
            try:
                return Course(**values)
            except ValidationError as exc:
                logger.info("Structured Course candidate rejected for %s: %s", url, exc)

        if not candidates and allow_dom_fallback:
            return Parser._parse_dom_fallback(html, url, defaults)
        return None


def parse_course_page(
    html: str,
    url: str,
    allow_dom_fallback: bool = True,
    defaults: dict[str, Any] | None = None,
) -> Course | None:
    return Parser.parse_course_page(
        html,
        url,
        allow_dom_fallback=allow_dom_fallback,
        defaults=defaults,
    )
