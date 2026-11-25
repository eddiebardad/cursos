"""Microsoft Learn catalog API provider."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Iterator
from typing import Any, ClassVar

from core.crawler import Crawler
from schemas.models import AccessType, Course, resolve_category
from utils.logger import get_logger

from .base import ProviderBase

logger = get_logger(__name__)

_API_URL = "https://learn.microsoft.com/api/catalog/"
_DEFAULT_LOCALE = "es-es"


class MicrosoftLearnProvider(ProviderBase):
    provider_name = "Microsoft Learn"
    provider_aliases: ClassVar[tuple[str, ...]] = (
        "ms_learn",
        "mslearn",
        "MicrosoftLearn",
    )
    default_url = f"{_API_URL}?locale={_DEFAULT_LOCALE}"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        hostname = urllib.parse.urlsplit(url).hostname or ""
        return hostname.casefold() == "learn.microsoft.com"

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        request_url, request_locale = self._catalog_request(url, enable_modules)
        logger.info("Fetching Microsoft Learn catalog: %s", request_url)

        with Crawler() as crawler:
            response_text = crawler.get(request_url)

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            logger.error("Microsoft Learn catalog returned invalid JSON: %s", exc)
            return
        if not isinstance(data, dict):
            logger.warning("Microsoft Learn catalog response was not a JSON object.")
            return

        items = self._collection(data.get("learningPaths"))
        if enable_modules:
            items.extend(self._collection(data.get("modules")))

        emitted = 0
        for item in items:
            course = self._map_to_course(item, request_locale)
            if course is None:
                continue
            yield course
            emitted += 1
            if limit > 0 and emitted >= limit:
                return

    @classmethod
    def _catalog_request(cls, url: str, enable_modules: bool) -> tuple[str, str]:
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

        locale = next(
            (value for key, value in query if key.casefold() == "locale" and value),
            None,
        )
        if locale is None:
            locale = cls._locale_from_path(parsed.path) or _DEFAULT_LOCALE
            query.append(("locale", locale))

        if not any(key.casefold() == "type" and value for key, value in query):
            requested_types = "learningPaths,modules" if enable_modules else "learningPaths"
            query.append(("type", requested_types))

        request_url = urllib.parse.urlunsplit(
            (
                "https",
                "learn.microsoft.com",
                "/api/catalog/",
                urllib.parse.urlencode(query),
                "",
            )
        )
        return request_url, locale

    @staticmethod
    def _locale_from_path(path: str) -> str | None:
        match = re.search(r"/([a-z]{2}(?:-[a-z]{2})?)(?:/|$)", path, flags=re.IGNORECASE)
        return match.group(1).casefold() if match else None

    @staticmethod
    def _collection(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _labels(value: Any) -> list[str]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = []
            for entry in value:
                if isinstance(entry, str):
                    values.append(entry)
                elif isinstance(entry, dict):
                    label = entry.get("name") or entry.get("title") or entry.get("slug")
                    if isinstance(label, str):
                        values.append(label)
        else:
            values = []
        return [re.sub(r"\s+", " ", label.replace("-", " ")).strip() for label in values if label.strip()]

    @classmethod
    def _map_to_course(cls, item: dict[str, Any], request_locale: str) -> Course | None:
        title = item.get("title")
        course_url = item.get("url")
        if not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(course_url, str) or not course_url.strip():
            return None

        duration_value = item.get("duration_in_minutes")
        if duration_value is None:
            duration_value = item.get("durationInMinutes")
        duration: str | None = None
        if (
            isinstance(duration_value, (int, float))
            and not isinstance(duration_value, bool)
            and duration_value > 0
        ):
            duration = str(int(duration_value)) if float(duration_value).is_integer() else str(duration_value)

        raw_levels = item.get("levels")
        level_values = cls._labels(raw_levels)
        level = level_values[0] if level_values else None

        subjects = cls._labels(item.get("subjects"))
        products = cls._labels(item.get("products"))
        roles = cls._labels(item.get("roles"))
        keywords = list(dict.fromkeys(subjects + products + roles))
        category = cls._category_for_signals(subjects, products, roles, title)

        item_locale = item.get("locale")
        locale = item_locale if isinstance(item_locale, str) and item_locale.strip() else request_locale
        language = re.split(r"[-_]", locale.strip(), maxsplit=1)[0].lower()

        image = item.get("icon_url") or item.get("social_image_url")
        if not isinstance(image, str):
            image = None
        summary = item.get("summary")
        description = summary if isinstance(summary, str) else None

        try:
            return Course(
                name=title,
                url=course_url,
                description=description,
                provider="Microsoft Learn",
                time_required=duration,
                educational_level=level,
                category=category,
                keywords=keywords or None,
                in_language=language,
                image=image,
                access_type=AccessType.free_with_certificate,
            )
        except ValueError as exc:
            logger.info("Skipping Microsoft Learn item %s: %s", course_url, exc)
            return None

    @staticmethod
    def _category_for_signals(
        subjects: list[str],
        products: list[str],
        roles: list[str],
        title: str,
    ) -> str:
        for signal in (*subjects, *products, *roles, title):
            category = resolve_category(category_hint=signal)
            if category != "Pendiente_Categoria":
                return category
        return "Pendiente_Categoria"
