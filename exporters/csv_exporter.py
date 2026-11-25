"""
exporters/csv_exporter.py
==============================================================================
Exportador CSV compatible con Omeka S Bulk Import / CSV Import.
Codificación UTF-8 pura (sin BOM), separador de listas ';' y cabeceras canónicas.
==============================================================================
"""

import csv
import io
import sys
from collections.abc import Iterable
from typing import Any

from exporters.base import BaseExporter
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

CSV_HEADERS: list[str] = [
    "dcterms:title",
    "dcterms:identifier",
    "dcterms:publisher",
    "dcterms:creator",
    "dcterms:description",
    "dcterms:language",
    "dcterms:subject",
    "schema:name",
    "schema:url",
    "schema:description",
    "schema:provider",
    "schema:author",
    "schema:about",
    "schema:keywords",
    "schema:timeRequired",
    "schema:educationalLevel",
    "schema:inLanguage",
    "schema:isAccessibleForFree",
    "schema:educationalCredentialAwarded",
    "schema:coursePrerequisites",
    "schema:image",
    "canonical_url",
    "content_hash",
    "access_type",
    "needs_review",
    "review_notes",
    "last_seen_at",
]


def _join_list(items: list[str] | None) -> str:
    """Escapa puntos y comas internos sustituyéndolos por comas antes de unir con ';'."""
    if not items:
        return ""
    clean_items = [item.replace(";", ",") for item in items]
    return ";".join(clean_items)


def course_to_csv_row(course: Course) -> dict[str, Any]:
    """Convierte una instancia de Course a un dict de fila CSV con cabeceras canónicas."""
    authors_str = _join_list(course.authors)
    keywords_str = _join_list(course.keywords)
    prereqs_str = _join_list(course.course_prerequisites)
    review_notes_str = _join_list(course.review_notes)
    cat_str = course.category if course.category and course.category != "Pendiente_Categoria" else ""

    return {
        "dcterms:title": course.name,
        "dcterms:identifier": course.canonical_url,
        "dcterms:publisher": course.provider or "",
        "dcterms:creator": authors_str,
        "dcterms:description": course.description or "",
        "dcterms:language": course.in_language or "",
        "dcterms:subject": cat_str,
        "schema:name": course.name,
        "schema:url": course.canonical_url,
        "schema:description": course.description or "",
        "schema:provider": course.provider or "",
        "schema:author": authors_str,
        "schema:about": cat_str,
        "schema:keywords": keywords_str,
        "schema:timeRequired": course.time_required or "",
        "schema:educationalLevel": course.educational_level or "",
        "schema:inLanguage": course.in_language or "",
        "schema:isAccessibleForFree": "true",
        "schema:educationalCredentialAwarded": course.access_type.credential_label_es,
        "schema:coursePrerequisites": prereqs_str,
        "schema:image": course.image or "",
        "canonical_url": course.canonical_url,
        "content_hash": course.content_hash,
        "access_type": course.access_type.value,
        "needs_review": str(course.needs_review).lower(),
        "review_notes": review_notes_str,
        "last_seen_at": course.last_seen_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class CSVExporter(BaseExporter):
    def export(self, courses: Iterable[Course], destination: str) -> None:
        course_list = list(courses)

        if destination == "-":
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")

            # Escribir a un buffer en memoria para evitar problemas de newline en Windows
            output_buffer = io.StringIO()
            writer = csv.DictWriter(output_buffer, fieldnames=CSV_HEADERS, lineterminator="\n")
            writer.writeheader()
            for c in course_list:
                writer.writerow(course_to_csv_row(c))

            sys.stdout.write(output_buffer.getvalue())
            sys.stdout.flush()
            logger.info(f"Emitidos {len(course_list)} cursos en formato CSV a stdout.")
        else:
            with open(destination, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, lineterminator="\n")
                writer.writeheader()
                for c in course_list:
                    writer.writerow(course_to_csv_row(c))

            logger.info(f"Exportados {len(course_list)} cursos a {destination} en formato CSV.")
