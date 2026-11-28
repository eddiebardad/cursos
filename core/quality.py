"""Batch validation for required provider metadata."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from core.exceptions import QualityGateError
from core.manifest import ProviderDefinition
from schemas.models import Course, resolve_language
from utils.logger import get_logger

logger = get_logger(__name__)

_BLOCKED_TITLES = {
    "403 forbidden",
    "404 not found",
    "access denied",
    "just a moment...",
    "page not found",
    "attention required!",
    "attention required! | cloudflare",
}
_LOGIN_SEGMENTS = {"login", "signin", "auth"}
_LANGUAGE_CODE = re.compile(r"^[a-z]{2}$", re.IGNORECASE)


class BatchQualityGate:
    """Keep valid course records and reject only batches that fail core metadata."""

    @staticmethod
    def validate(
        raw_courses: Iterable[Course | dict[str, Any]],
        provider: ProviderDefinition,
    ) -> list[Course]:
        candidates = list(raw_courses)
        if not candidates:
            return []

        valid: list[Course] = []
        rejected: list[str] = []
        seen_urls: set[str] = set()
        total = 0
        for index, raw_course in enumerate(candidates):
            try:
                course = (
                    raw_course
                    if isinstance(raw_course, Course)
                    else Course.model_validate(raw_course)
                )
            except (ValidationError, ValueError, TypeError) as exc:
                total += 1
                rejected.append(f"record {index}: {exc}")
                continue

            reason = BatchQualityGate._invalid_reason(course, provider)
            if reason:
                total += 1
                rejected.append(f"{course.name!r}: {reason}")
            elif course.canonical_url in seen_urls:
                logger.warning(
                    "BatchQualityGate skipped duplicate provider=%s canonical_url=%s",
                    provider.id,
                    course.canonical_url,
                )
            else:
                total += 1
                seen_urls.add(course.canonical_url)
                valid.append(course)

        rejected_count = len(rejected)
        if rejected_count:
            for reason in rejected:
                logger.warning(
                    "BatchQualityGate rejected provider=%s reason=%s",
                    provider.id,
                    reason,
                )
        if not valid or rejected_count / total > 0.5:
            raise QualityGateError(
                f"Quality gate rejected provider={provider.id}: "
                f"{len(valid)} valid, {rejected_count}/{total} rejected; "
                f"causes: {'; '.join(rejected)}"
            )

        if total >= 5 and all(not course.description for course in valid):
            logger.warning(
                "BatchQualityGate provider=%s: every course lacks a description",
                provider.id,
            )
        if total >= 5 and all(course.category == "Pendiente_Categoria" for course in valid):
            logger.warning(
                "BatchQualityGate provider=%s: every course has Pendiente_Categoria",
                provider.id,
            )
        return valid

    @staticmethod
    def _invalid_reason(
        course: Course,
        provider: ProviderDefinition,
    ) -> str | None:
        title = course.name.strip()
        if not title:
            return "missing title"
        if title.casefold() in _BLOCKED_TITLES:
            return "blocked/error title"

        for raw_url in (course.url, course.canonical_url):
            try:
                parsed = urlsplit(raw_url)
                host = (parsed.hostname or "").casefold().rstrip(".")
                port = parsed.port
            except ValueError:
                return "URL is malformed"
            if (
                parsed.scheme.casefold() != "https"
                or not host
                or parsed.username is not None
                or parsed.password is not None
                or port not in {None, 443}
                or host not in provider.allowed_hosts
            ):
                return "URL must use HTTPS, contain no credentials, and use an allowed provider host"
            if host == "localhost" or host.endswith((".localhost", ".local")):
                return "URL must not point to a local destination"
            try:
                address = ipaddress.ip_address(host.split("%", 1)[0])
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                return "URL must not point to a non-public IP address"
            if not parsed.path or parsed.path == "/":
                return "URL must point to a resource path"
            if any(
                segment.casefold() in _LOGIN_SEGMENTS
                for segment in parsed.path.split("/")
            ):
                return "URL points to a login/authentication path"
        if not course.provider or not course.provider.strip():
            return "missing provider"
        if course.is_accessible_for_free is not True:
            return "course is not explicitly free"
        if (
            not course.in_language
            or not _LANGUAGE_CODE.fullmatch(course.in_language)
            or resolve_language(course.in_language) != course.in_language
        ):
            return "missing or invalid language code"
        return None
