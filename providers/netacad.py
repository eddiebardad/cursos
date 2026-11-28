"""Cisco Networking Academy provider for its rendered public catalog."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterator
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from pydantic import ValidationError

from core.crawler import Crawler
from core.extractor import extract_course_candidates
from core.parser import parse_course_page
from schemas.models import AccessType, Course, resolve_category
from utils.logger import get_logger

from .base import ProviderBase

logger = get_logger(__name__)

_CATALOG_URL = "https://www.netacad.com/catalogs/learn?category=course"
_COURSE_LINK_WAIT = """() => [...document.querySelectorAll('a[href]')].some(anchor => {
    const path = new URL(anchor.href).pathname;
    const parts = path.split('/').filter(Boolean);
    return parts.length === 2 && parts[0] === 'courses' && parts[1] !== 'all-courses';
})"""


class NetacadProvider(ProviderBase):
    provider_name = "Netacad"
    provider_aliases: ClassVar[tuple[str, ...]] = ("netacad", "cisco", "cisco netacad")
    allowed_hosts: ClassVar[tuple[str, ...]] = ("netacad.com", "www.netacad.com")
    default_url = "https://www.netacad.com/courses/all-courses"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        hostname = (urllib.parse.urlsplit(url).hostname or "").casefold()
        return hostname in {"netacad.com", "www.netacad.com"}

    def should_crawl(self, url: str) -> bool:
        return False

    @staticmethod
    def _is_course_detail_url(url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        return (
            (parsed.hostname or "").casefold() in {"netacad.com", "www.netacad.com"}
            and len(parts) == 2
            and parts[0].casefold() == "courses"
            and parts[1].casefold() != "all-courses"
        )

    @staticmethod
    def _is_explicitly_free(text: str) -> bool:
        return bool(
            re.search(r"\bPrice\s*:\s*(?:Free|Gratis)\b", text, flags=re.IGNORECASE)
        )

    @staticmethod
    def _access_type(text: str) -> AccessType:
        if re.search(
            r"\bfree\s+(?:digital\s+)?(?:certificate|badge)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return AccessType.free_with_certificate
        return AccessType.free_no_certificate

    @staticmethod
    def _page_language(url: str, fallback: str | None) -> str | None:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        course_language = next(
            (values[0] for key, values in query.items() if key.casefold() == "courselang" and values),
            None,
        )
        if course_language:
            return course_language
        return fallback

    @staticmethod
    def _card_description(card: Tag, name: str) -> str | None:
        description = card.find(
            lambda tag: isinstance(tag, Tag)
            and "description" in str(tag.get("class")).casefold()
        )
        if isinstance(description, Tag):
            title = description.get("title")
            value = str(title).strip() if title else description.get_text(" ", strip=True)
            if value:
                return value

        aria_label = card.get("aria-label")
        if isinstance(aria_label, str):
            label = aria_label.strip()
            if label.casefold().startswith(name.casefold()):
                remainder = label[len(name) :].lstrip(" .:-")
                return remainder or None
        return None

    @staticmethod
    def _card_section(card: Tag) -> str | None:
        for heading in card.find_all_previous(["h2", "h3", "h4"], limit=8):
            label = heading.get_text(" ", strip=True)
            if label and label.casefold() not in {
                "learning catalog",
                "courses",
                "course",
                "home",
            }:
                return label
        return None

    @classmethod
    def _course_from_card(
        cls,
        card: Tag,
        url: str,
        page_language: str | None,
    ) -> Course | None:
        card_text = card.get_text(" ", strip=True)
        if not cls._is_explicitly_free(card_text):
            return None

        heading = card.select_one('[role="heading"]')
        name = heading.get_text(" ", strip=True) if isinstance(heading, Tag) else ""
        if not name:
            aria_label = card.get("aria-label")
            name = str(aria_label).split(".", maxsplit=1)[0].strip() if aria_label else ""
        if not name:
            return None

        description = cls._card_description(card, name)
        duration_match = re.search(
            r"\bDuration\s*:\s*(\d+(?:[.,]\d+)?\s*(?:hours?|hrs?|minutes?|mins?))",
            card_text,
            flags=re.IGNORECASE,
        )
        level_match = re.search(
            r"\bDifficulty\s+level\s*:\s*(Beginner|Intermediate|Advanced|Expert)\b",
            card_text,
            flags=re.IGNORECASE,
        )
        section = cls._card_section(card)
        category = resolve_category(
            category_hint=section or f"{name} {description or ''}",
        )
        image_tag = card.find("img", src=True)
        image = str(image_tag.get("src")) if isinstance(image_tag, Tag) else None
        language = cls._page_language(url, page_language)

        try:
            return Course(
                name=name,
                url=url,
                description=description,
                provider="Netacad",
                category=category,
                keywords=[section] if section else None,
                time_required=duration_match.group(1) if duration_match else None,
                educational_level=level_match.group(1) if level_match else None,
                in_language=language,
                image=image,
                access_type=cls._access_type(card_text),
                is_accessible_for_free=True,
            )
        except (ValidationError, ValueError) as exc:
            logger.info("NetAcad card rejected for %s: %s", url, exc)
            return None

    @classmethod
    def _courses_from_catalog(cls, html: str, catalog_url: str) -> list[Course]:
        soup = BeautifulSoup(html, "html.parser")
        html_element = soup.find("html")
        page_language = (
            str(html_element.get("lang"))
            if html_element and html_element.get("lang")
            else None
        )
        courses: list[Course] = []
        seen_urls: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(catalog_url, str(anchor["href"]))
            parsed = urllib.parse.urlsplit(href)
            if (parsed.hostname or "").casefold() not in {"netacad.com", "www.netacad.com"}:
                continue
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 2 or parts[0].casefold() != "courses":
                continue
            course_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
            )
            if course_url in seen_urls:
                continue
            seen_urls.add(course_url)

            course = cls._course_from_card(anchor, course_url, page_language)
            if course is not None:
                courses.append(course)
        return courses

    @classmethod
    def _course_from_detail(cls, html: str, url: str) -> Course | None:
        candidates = extract_course_candidates(html, url)
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        if not cls._is_explicitly_free(page_text):
            return None

        defaults = {
            "provider": "Netacad",
            "access_type": cls._access_type(page_text),
            "is_accessible_for_free": True,
        }
        for candidate in candidates:
            values = {**candidate, **defaults}
            try:
                return Course(**values)
            except (ValidationError, ValueError) as exc:
                logger.info("NetAcad structured Course rejected for %s: %s", url, exc)
        if candidates:
            return None
        return parse_course_page(html, url, defaults=defaults)

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        target_url = url or _CATALOG_URL
        with Crawler(render=True) as crawler:
            if self._is_course_detail_url(target_url):
                with crawler.open_page(
                    target_url,
                    allowed_hosts=self.allowed_hosts,
                    reject_login_path=True,
                ) as page:
                    html = page.content()
                course = self._course_from_detail(html, target_url)
                if course is not None:
                    yield course
                return

            with crawler.open_page(
                target_url,
                allowed_hosts=self.allowed_hosts,
                reject_login_path=True,
            ) as page:
                try:
                    page.wait_for_function(_COURSE_LINK_WAIT, timeout=15_000)
                except PlaywrightTimeoutError:
                    logger.warning("NetAcad catalog did not render course links within 15 seconds.")
                html = page.content()

            courses = self._courses_from_catalog(html, target_url)
            if not courses:
                logger.warning("No explicitly free NetAcad course cards were rendered.")
                return

            emitted = 0
            for course in courses:
                yield course
                emitted += 1
                if limit > 0 and emitted >= limit:
                    return
