"""
exporters/jsonld_exporter.py
==============================================================================
Exportador JSON-LD compatible con la API REST de Omeka S v4+, OAI-PMH
y metadatos privados para n8n.
==============================================================================
"""

import json
import sys
from collections.abc import Iterable
from typing import Any

from exporters.base import BaseExporter
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)


def course_to_omeka_jsonld(course: Course) -> dict[str, Any]:
    """
    Convierte una instancia de Course a un objeto JSON-LD compatible al 100%
    con la API REST de Omeka S v4+ (ARCHITECTURE.md §6.1).
    """
    item: dict[str, Any] = {
        "@type": ["o:Item", "schema:Course"],
        "o:is_public": False,
    }

    # Helpers para construir valores compatibles con Omeka S v4+
    def add_literal(prop: str, val: Any, lang: str | None = None, is_public: bool = True) -> None:
        if val is None:
            return
        entry: dict[str, Any] = {
            "type": "literal",
            "property_id": "auto",
            "@value": str(val),
        }
        if lang is not None:
            entry["@language"] = lang
        if not is_public:
            entry["is_public"] = False
        item.setdefault(prop, []).append(entry)

    def add_uri(prop: str, url_val: str | None, is_public: bool = True) -> None:
        if not url_val:
            return
        entry: dict[str, Any] = {
            "type": "uri",
            "property_id": "auto",
            "@id": str(url_val),
        }
        if not is_public:
            entry["is_public"] = False
        item.setdefault(prop, []).append(entry)

    # 1. Propiedades públicas schema:*
    add_literal("schema:name", course.name, lang=course.in_language)
    add_uri("schema:url", course.canonical_url)

    if course.description:
        add_literal("schema:description", course.description, lang=course.in_language)

    if course.provider:
        add_literal("schema:provider", course.provider)

    if course.authors:
        for author in course.authors:
            add_literal("schema:author", author)

    if course.category:
        add_literal("schema:about", course.category)

    if course.keywords:
        for kw in course.keywords:
            add_literal("schema:keywords", kw)

    if course.time_required:
        add_literal("schema:timeRequired", course.time_required)

    if course.educational_level:
        add_literal("schema:educationalLevel", course.educational_level)

    if course.in_language:
        add_literal("schema:inLanguage", course.in_language)

    add_literal("schema:isAccessibleForFree", "true")
    add_literal(
        "schema:educationalCredentialAwarded",
        course.access_type.credential_label_es,
    )

    if course.course_prerequisites:
        for prereq in course.course_prerequisites:
            add_literal("schema:coursePrerequisites", prereq)

    if course.image:
        add_uri("schema:image", course.image)

    # 2. Propiedades privadas nativas de Omeka S ("is_public": False)
    add_literal(
        "schema:identifier",
        f"urn:cursodex:sha256:{course.content_hash}",
        is_public=False,
    )
    add_literal(
        "schema:dateModified",
        course.last_seen_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        is_public=False,
    )

    # 3. Espejo Dublin Core para OAI-PMH (oai_dc)
    add_literal("dcterms:title", course.name)
    add_literal("dcterms:identifier", course.canonical_url)

    if course.description:
        add_literal("dcterms:description", course.description)

    if course.provider:
        add_literal("dcterms:publisher", course.provider)

    if course.authors:
        for author in course.authors:
            add_literal("dcterms:creator", author)

    if course.in_language:
        add_literal("dcterms:language", course.in_language)

    if course.category:
        add_literal("dcterms:subject", course.category)

    # 4. Bloque de metadatos privados _cursodex_meta para n8n
    item["_cursodex_meta"] = {
        "canonical_url": course.canonical_url,
        "content_hash": course.content_hash,
        "access_type": course.access_type.value,
        "last_seen_at": course.last_seen_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "needs_review": course.needs_review,
        "review_notes": list(course.review_notes),
    }

    return item


class JSONLDExporter(BaseExporter):
    def export(self, courses: Iterable[Course], destination: str) -> None:
        course_list = list(courses)
        items = [course_to_omeka_jsonld(c) for c in course_list]

        if destination == "-":
            # Asegurar codificación UTF-8 en stdout (Windows y Unix)
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")

            if not items:
                sys.stdout.write("[]\n")
            else:
                sys.stdout.write(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
            sys.stdout.flush()
            logger.info(f"Emitidos {len(items)} cursos en formato JSON-LD a stdout.")
        else:
            with open(destination, mode="w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
                f.write("\n")
            logger.info(f"Exportados {len(items)} cursos a {destination} en formato JSON-LD.")
