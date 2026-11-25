"""Aprende.org course provider backed by its public catalog API."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator
from typing import Any, ClassVar

from pydantic import ValidationError

from core.crawler import Crawler
from core.exceptions import ParsingError
from schemas.models import AccessType, Course
from utils.logger import get_logger

from .base import ProviderBase

logger = get_logger(__name__)

_API_ROOT = "https://besvc.capacitateparaelempleo.org"
_COURSES_URL = f"{_API_ROOT}/api/Courses?platformId=2"
_API_HEADERS = {
    "includeHATEOAS": "N",
    "platformId": "2",
    "x-languageCode": "es",
    "x-isApp": "false",
    "X-API-KEY": "",
}


class AprendeProvider(ProviderBase):
    provider_name = "Aprende"
    provider_aliases: ClassVar[tuple[str, ...]] = ("aprende", "capacitate")
    default_url = "https://aprende.org/cursos"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        hostname = (urllib.parse.urlsplit(url).hostname or "").casefold()
        return hostname in {"aprende.org", "www.aprende.org"}

    def should_crawl(self, url: str) -> bool:
        return False

    @staticmethod
    def _decode_json(raw: str, url: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ParsingError(f"Aprende API returned invalid JSON from {url}: {exc}") from exc

    def _fetch_detail(self, crawler: Crawler, course_id: int | str) -> dict[str, Any]:
        detail_url = f"{_API_ROOT}/api/Courses/{course_id}?platformId=2"
        detail = self._decode_json(crawler.get(detail_url, headers=_API_HEADERS), detail_url)
        if not isinstance(detail, dict):
            raise ParsingError(f"Aprende detail API returned a non-object for course {course_id}")
        return detail

    @staticmethod
    def _labels(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if not isinstance(value, list):
            return []
        labels: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                labels.append(item)
            elif isinstance(item, dict):
                label = item.get("name") or item.get("title")
                if isinstance(label, str) and label.strip():
                    labels.append(label)
        return labels

    def _map_to_course(self, item: dict[str, Any]) -> Course | None:
        course_id = item.get("id")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            logger.warning("Skipping Aprende record with missing name (id=%s).", course_id)
            return None

        permalink = (
            f"https://aprende.org/cursos/view/{course_id}"
            if isinstance(course_id, (int, str)) and str(course_id).isdigit()
            else None
        )
        if permalink is None:
            logger.warning("Skipping Aprende record with invalid id (%s).", course_id)
            return None

        sector = item.get("sector")
        category = sector.get("name") if isinstance(sector, dict) else None
        if not isinstance(category, str):
            category = None

        keywords: list[str] = []
        for field in ("competences", "catalogs", "linkCourses"):
            keywords.extend(self._labels(item.get(field)))

        raw_level = item.get("difficultyId")
        difficulty_map = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}
        try:
            level = difficulty_map.get(int(raw_level)) if raw_level is not None else None
        except (TypeError, ValueError):
            level = str(raw_level) if raw_level else None

        description_value = item.get("description")
        description = description_value if isinstance(description_value, str) else None
        duration_value = next(
            (
                item.get(field)
                for field in ("durationInMinutes", "durationMinutes", "duration")
                if item.get(field) is not None
            ),
            None,
        )

        try:
            return Course(
                name=name,
                description=description,
                url=permalink,
                image=item.get("imageUrl") if isinstance(item.get("imageUrl"), str) else None,
                provider="Aprende.org (Fundación Carlos Slim)",
                in_language="es",
                access_type=AccessType.free_with_certificate,
                educational_level=level,
                time_required=duration_value,
                keywords=keywords or None,
                category=category,
            )
        except (ValidationError, ValueError) as exc:
            logger.warning("Could not create Aprende Course for id=%s: %s", course_id, exc)
            return None

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        logger.info("Fetching Aprende catalog from %s", _COURSES_URL)
        with Crawler() as crawler:
            data = self._decode_json(crawler.get(_COURSES_URL, headers=_API_HEADERS), _COURSES_URL)
            if not isinstance(data, dict) or not isinstance(data.get("courses"), list):
                raise ParsingError("Aprende catalog response must contain a courses array")

            seen_ids: set[str] = set()
            emitted = 0
            for record in data["courses"]:
                if not isinstance(record, dict):
                    continue
                course_id = record.get("id")
                if course_id is not None:
                    id_key = str(course_id)
                    if id_key in seen_ids:
                        continue
                    seen_ids.add(id_key)

                course = self._map_to_course(record)
                if course is None:
                    continue

                if course.description is None and isinstance(course_id, (int, str)):
                    detail = self._fetch_detail(crawler, course_id)
                    merged = {**record, **{key: value for key, value in detail.items() if value is not None}}
                    course = self._map_to_course(merged) or course

                yield course
                emitted += 1
                if limit > 0 and emitted >= limit:
                    return
