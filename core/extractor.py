"""Semantic course extraction backed by extruct."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin, urlsplit

import extruct

from schemas.models import AccessType
from utils.logger import get_logger

logger = get_logger(__name__)

_TEXT_KEYS = ("name", "targetName", "description", "@value", "alternateName", "headline")
_SCHEMA_NAMESPACES = ("http://schema.org/", "https://schema.org/")


def _is_course_type(type_value: Any) -> bool:
    type_values = type_value if isinstance(type_value, list) else [type_value]
    for value in type_values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().rstrip("/").casefold()
        if normalized in {"course", "schema:course"}:
            return True
        if any(normalized == f"{namespace}course" for namespace in _SCHEMA_NAMESPACES):
            return True
    return False


def _iter_course_objects(data: Any) -> Iterator[dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            yield from _iter_course_objects(item)
        return

    if not isinstance(data, dict):
        return

    course_type = data.get("@type")
    if _is_course_type(course_type):
        yield data
    elif _is_course_type(data.get("type")) and isinstance(data.get("properties"), dict):
        properties = dict(data["properties"])
        properties["@type"] = data["type"]
        yield properties

    for value in data.values():
        if isinstance(value, (dict, list)):
            yield from _iter_course_objects(value)


def _text_values(value: Any, keys: tuple[str, ...] = _TEXT_KEYS) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_text_values(item, keys))
        return result
    if not isinstance(value, dict):
        return []

    properties = value.get("properties")
    if isinstance(properties, dict):
        return _text_values(properties, keys)
    for key in keys:
        if key in value:
            values = _text_values(value[key], keys)
            if values:
                return values
    return []


def _first_text(value: Any, keys: tuple[str, ...] = _TEXT_KEYS) -> str | None:
    values = _text_values(value, keys)
    return values[0] if values else None


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "" and value != [] and value != {}:
            return value
    return None


def _first_text_field(
    data: dict[str, Any],
    keys: tuple[str, ...],
    text_keys: tuple[str, ...] = _TEXT_KEYS,
) -> str | None:
    for key in keys:
        value = _first_text(data.get(key), text_keys)
        if value is not None:
            return value
    return None


def _course_instance_values(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for instance in _as_list(data.get("hasCourseInstance")):
        if not isinstance(instance, dict):
            continue
        properties = instance.get("properties")
        instance_data = properties if isinstance(properties, dict) else instance
        value = _first_present(instance_data, keys)
        if value is not None:
            return value
    return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _normalize_language(value: Any) -> str | None:
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            value = properties
        if isinstance(value, dict):
            value = _first_present(value, ("alternateName", "name", "code", "identifier"))
    language = _first_text(value)
    if language is None:
        return None
    language = language.strip()
    if "-" in language or "_" in language:
        return re.split(r"[-_]", language, maxsplit=1)[0].lower()
    return language


def _normalize_keywords(value: Any) -> list[str] | None:
    items: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            items.extend(part.strip() for part in re.split(r"[,;]", item) if part.strip())
        else:
            items.extend(_text_values(item))
    return items or None


def _is_explicit_false(value: Any) -> bool:
    if value is False:
        return True
    return isinstance(value, str) and value.strip().casefold() in {"false", "0", "no"}


def _is_explicit_true(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, str) and value.strip().casefold() in {"true", "1", "yes"}


def _offer_prices(value: Any) -> list[float]:
    prices: list[float] = []
    for offer in _as_list(value):
        if not isinstance(offer, dict):
            continue
        price = offer.get("price")
        if isinstance(price, dict):
            price = price.get("@value")
        try:
            if price is not None:
                prices.append(float(price))
        except (TypeError, ValueError):
            continue
    return prices


def _access_type(data: dict[str, Any]) -> AccessType | None:
    credential_text = " ".join(
        _text_values(data.get("educationalCredentialAwarded"))
    ).casefold()
    indicates_free_credential = (
        any(word in credential_text for word in ("free", "gratuit"))
        and any(
            word in credential_text
            for word in ("certificate", "certificado", "badge", "insignia", "credential")
        )
    )
    return AccessType.free_with_certificate if indicates_free_credential else None


def _candidate_to_course_data(candidate: dict[str, Any], base_url: str) -> dict[str, Any]:
    name = _first_text_field(candidate, ("name", "headline"))
    description = _first_text_field(candidate, ("description", "abstract"))

    raw_url = _first_present(candidate, ("url", "@id"))
    if isinstance(raw_url, dict):
        raw_url = _first_text(raw_url, ("@id", "url"))
    if not isinstance(raw_url, str) or urlsplit(urljoin(base_url, raw_url)).scheme not in {
        "http",
        "https",
    }:
        raw_url = base_url
    course_url = urljoin(base_url, raw_url)
    if urlsplit(course_url).scheme not in {"http", "https"} or not urlsplit(course_url).netloc:
        course_url = base_url

    provider = _first_text_field(candidate, ("provider", "publisher"), ("name",))

    authors: list[str] = []
    for key in ("author", "creator", "instructor"):
        authors = _text_values(candidate.get(key), ("name",))
        if authors:
            break
    if not authors:
        for key in ("author", "creator", "instructor"):
            instance_value = _course_instance_values(candidate, (key,))
            author_names = _text_values(instance_value, ("name",))
            if author_names:
                authors = author_names
                break

    language_value = _first_present(candidate, ("inLanguage",))
    if language_value is None:
        language_value = _course_instance_values(candidate, ("inLanguage",))

    duration_value = _first_present(candidate, ("timeRequired", "courseWorkload"))
    if duration_value is None:
        duration_value = _course_instance_values(
            candidate,
            ("timeRequired", "courseWorkload"),
        )
    duration = _first_text(duration_value, ("@value", "name"))
    if isinstance(duration_value, (int, float)):
        duration = str(duration_value)

    education_level = _first_text_field(candidate, ("educationalLevel",), ("name",))
    category = _first_text_field(
        candidate,
        ("about", "teaches", "educationalAlignment"),
    )
    prerequisites = _text_values(
        _first_present(candidate, ("coursePrerequisites", "competencyRequired")),
        ("name", "description"),
    )

    image_value = _first_present(candidate, ("image", "thumbnailUrl"))
    image = _first_text(image_value, ("url", "contentUrl", "@id"))

    free_access = candidate.get("isAccessibleForFree")
    if _is_explicit_false(free_access):
        is_accessible_for_free = False
    elif _is_explicit_true(free_access):
        is_accessible_for_free = True
    else:
        prices = _offer_prices(candidate.get("offers"))
        is_accessible_for_free = not (any(price > 0 for price in prices) and 0 not in prices)

    result: dict[str, Any] = {
        "name": name,
        "url": course_url,
        "description": description,
        "provider": provider,
        "authors": authors or None,
        "in_language": _normalize_language(language_value),
        "time_required": duration,
        "educational_level": education_level,
        "category": category,
        "keywords": _normalize_keywords(candidate.get("keywords")),
        "course_prerequisites": prerequisites or None,
        "image": image,
        "is_accessible_for_free": is_accessible_for_free,
    }
    access_type = _access_type(candidate)
    if access_type is not None:
        result["access_type"] = access_type
    return {key: value for key, value in result.items() if value is not None}


def _open_graph_properties(value: Any) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for graph in _as_list(value):
        if not isinstance(graph, dict):
            continue
        pairs = graph.get("properties")
        if not isinstance(pairs, list):
            continue
        for pair in pairs:
            if (
                isinstance(pair, (list, tuple))
                and len(pair) == 2
                and isinstance(pair[0], str)
            ):
                properties.setdefault(pair[0].casefold(), pair[1])
    return properties


def extract_open_graph_metadata(html: str, base_url: str) -> dict[str, Any]:
    """Extract OpenGraph properties without treating them as Course evidence."""
    try:
        extracted = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["opengraph"],
            uniform=False,
            errors="ignore",
        )
    except Exception as exc:
        logger.debug("OpenGraph extraction failed for %s: %s", base_url, exc)
        return {}
    return _open_graph_properties(extracted.get("opengraph", []))


def _enrich_with_open_graph(
    candidate: dict[str, Any],
    og_properties: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(candidate)
    for target, source in (
        ("name", "og:title"),
        ("description", "og:description"),
        ("image", "og:image"),
        ("inLanguage", "og:locale"),
    ):
        if not enriched.get(target) and og_properties.get(source):
            enriched[target] = og_properties[source]
    return enriched


def extract_course_candidates(html: str, base_url: str) -> list[dict[str, Any]]:
    """Extract Schema.org Course records, preferring JSON-LD to Microdata."""
    try:
        extracted = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=False,
            errors="ignore",
        )
    except Exception as exc:
        logger.debug("extruct failed for %s: %s", base_url, exc)
        return []

    og_properties = _open_graph_properties(extracted.get("opengraph", []))
    result: list[dict[str, Any]] = []
    for syntax in ("json-ld", "microdata"):
        for candidate in _iter_course_objects(extracted.get(syntax, [])):
            enriched = _enrich_with_open_graph(candidate, og_properties)
            result.append(_candidate_to_course_data(enriched, base_url))
    return result
