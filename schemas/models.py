"""
schemas/models.py
==============================================================================
Modelo estático Pydantic v2 para Cursodex (v0.2.0).

Cumple estrictamente los contratos de normalización semántica, detección de cambios
(content_hash SHA-256), canonización de URLs (anti-redirección de portada),
filtro contra falsos gratis, normalización ISO 8601 de duraciones y mapeo
declarativo de categorías CINE-F 2013 / DigComp 2.2.
==============================================================================
"""

from __future__ import annotations

import functools
import hashlib
import html
import json
import re
import unicodedata
import urllib.parse
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ==============================================================================
# Enum de Tipos de Acceso / Certificación
# ==============================================================================
class AccessType(StrEnum):
    free_with_certificate = "free_with_certificate"
    free_audit_paid_certificate = "free_audit_paid_certificate"
    free_no_certificate = "free_no_certificate"

    @property
    def credential_label_es(self) -> str:
        """Etiqueta normalizada en español para schema:educationalCredentialAwarded."""
        mapping = {
            AccessType.free_with_certificate: "Certificado gratuito",
            AccessType.free_audit_paid_certificate: "Acceso gratuito (certificado de pago)",
            AccessType.free_no_certificate: "Curso gratuito (sin certificado)",
        }
        return mapping[self]


# ==============================================================================
# Carga y caché del vocabulario controlado (vocab_map.yml)
# ==============================================================================
@functools.lru_cache(maxsize=1)
def get_vocab_map() -> dict[str, Any]:
    """Carga mappings/vocab_map.yml relativo a la raíz del repositorio."""
    vocab_path = Path(__file__).resolve().parent.parent / "mappings" / "vocab_map.yml"
    if not vocab_path.exists():
        raise FileNotFoundError(f"Archivo de vocabulario no encontrado en {vocab_path}")
    with open(vocab_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


# ==============================================================================
# Helpers de normalización de texto y matching con límites de palabra
# ==============================================================================
def clean_text_field(text: str | None) -> str | None:
    """
    Limpia entidades HTML, retira etiquetas HTML y colapsa espacios en blanco.
    Devuelve None si el resultado está vacío.
    """
    if not text or not str(text).strip():
        return None
    t = html.unescape(str(text))
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if t else None


def clean_and_dedup_list(items: list[str] | None) -> list[str] | None:
    """
    Limpia cada elemento de una lista de texto, retira duplicados respetando
    el orden (comparación case-insensitive) y omite vacíos.
    """
    if not items:
        return None
    seen_lower: set[str] = set()
    deduped: list[str] = []
    for raw in items:
        cleaned = clean_text_field(raw)
        if not cleaned:
            continue
        lower_key = cleaned.lower()
        if lower_key not in seen_lower:
            seen_lower.add(lower_key)
            deduped.append(cleaned)
    return deduped if deduped else None


def normalize_text_for_matching(text: str) -> str:
    """Convierte a minúsculas y retira acentos/diacríticos."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def match_synonym_boundary(synonym: str, text: str) -> bool:
    """
    Comprueba si synonym coincide con text usando límites estrictos de palabra
    (caracteres no alfanuméricos). Evita colisiones de palabras cortas
    (ej. 'ia', 'ai', 'it', 'ti', 'r', 'c') dentro de palabras como
    'historia', 'literatura' o 'arquitectura'.
    """
    norm_syn = normalize_text_for_matching(synonym)
    norm_text = normalize_text_for_matching(text)
    pattern = rf"(?<![a-z0-9]){re.escape(norm_syn)}(?![a-z0-9])"
    return bool(re.search(pattern, norm_text))


def resolve_category(
    category_hint: str | None = None,
    keywords: list[str] | None = None,
    title: str | None = None,
) -> str:
    """
    Resuelve la categoría canónica evaluando las reglas de mappings/vocab_map.yml
    estrictamente DE MÁS ESPECÍFICA A MÁS GENERAL.
    Si ninguna regla coincide, devuelve 'Pendiente_Categoria'.
    """
    vocab = get_vocab_map()
    categories_list = vocab.get("categories", [])

    sources: list[str] = []
    if category_hint and category_hint.strip():
        sources.append(category_hint.strip())
    if keywords:
        sources.extend([kw.strip() for kw in keywords if kw and kw.strip()])
    if title and title.strip():
        sources.append(title.strip())

    if not sources:
        return "Pendiente_Categoria"

    for cat_entry in categories_list:
        canonical = cat_entry.get("canonical")
        synonyms = cat_entry.get("synonyms", [])
        if not canonical:
            continue

        if category_hint and normalize_text_for_matching(category_hint) == normalize_text_for_matching(canonical):
            return canonical

        for syn in synonyms:
            for text_source in sources:
                if match_synonym_boundary(syn, text_source):
                    return canonical

    return "Pendiente_Categoria"


def resolve_educational_level(level_raw: str | None) -> str | None:
    """Mapea el nivel educativo a Principiante, Intermedio o Avanzado."""
    if not level_raw or not str(level_raw).strip():
        return None

    norm_raw = normalize_text_for_matching(str(level_raw).strip())
    vocab = get_vocab_map()
    levels_map = vocab.get("educational_levels", {})

    for canonical, syns in levels_map.items():
        for syn in syns:
            if match_synonym_boundary(syn, norm_raw):
                return canonical
    return None


def resolve_language(lang_raw: str | None) -> str | None:
    """Normaliza el idioma al código ISO 639-1 de 2 letras en minúsculas."""
    if not lang_raw or not str(lang_raw).strip():
        return None

    raw = str(lang_raw).strip().lower()
    vocab = get_vocab_map()
    languages_map = vocab.get("languages", {})

    for iso_code, syns in languages_map.items():
        if raw == iso_code or raw in [s.lower() for s in syns]:
            return iso_code

    for iso_code, syns in languages_map.items():
        for syn in syns:
            if match_synonym_boundary(syn, raw):
                return iso_code

    if len(raw) >= 2 and raw[:2].isalpha():
        candidate = raw[:2]
        if candidate in languages_map:
            return candidate

    return None


# ==============================================================================
# Helper de canonización de URL (anti-redirección de portada y deduplicación)
# ==============================================================================
TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "_hsenc",
    "_hsmi",
    "mkt_tok",
}


def canonicalize_url(raw_url: str) -> str:
    """
    Normaliza una URL externa garantizando:
    1. Esquema forzado a 'https'.
    2. Dominio en minúsculas y sin puertos redundantes.
    3. Ruta preservando mayúsculas/minúsculas, sin barra final.
    4. Eliminación de fragmentos (#...).
    5. Filtrado estricto de parámetros de rastreo (utm_*, fbclid, etc.).
    6. Preservación y ordenación alfabética de query params legítimos (?id=1&lang=es).
    7. Lanzamiento de ValueError si la URL carece de ruta de recurso (redirección a portada).
    """
    if not raw_url or not raw_url.strip():
        raise ValueError("La URL no puede estar vacía.")

    parsed = urllib.parse.urlsplit(raw_url.strip())
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL inválida sin dominio: '{raw_url}'")

    port = parsed.port
    if port and port not in (80, 443):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = parsed.path
    if not path or path.strip("/") == "":
        raise ValueError(
            f"La URL canónica carece de ruta de recurso (redirección a portada detectada): '{raw_url}'"
        )

    clean_path = "/" + path.strip("/")

    qsl = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    clean_qsl: list[tuple[str, str]] = []
    for k, v in qsl:
        k_lower = k.lower()
        if k_lower.startswith("utm_") or k_lower in TRACKING_QUERY_PARAMS:
            continue
        clean_qsl.append((k, v))

    clean_qsl.sort(key=lambda item: item[0])
    clean_query = urllib.parse.urlencode(clean_qsl)

    return urllib.parse.urlunsplit(("https", netloc, clean_path, clean_query, ""))


# ==============================================================================
# Helper de normalización de duración (ISO 8601)
# ==============================================================================
ISO_DURATION_REGEX = re.compile(
    r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def format_iso_duration_minutes(total_minutes: int) -> str:
    """Convierte minutos totales a string ISO 8601 (ej. 90 -> 'PT1H30M')."""
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0 and minutes > 0:
        return f"PT{hours}H{minutes}M"
    elif hours > 0:
        return f"PT{hours}H"
    elif minutes > 0:
        return f"PT{minutes}M"
    return "PT0M"


def parse_and_normalize_duration(val: Any) -> tuple[str | None, bool]:
    """
    Interpreta duraciones en ISO 8601, enteros/flotantes en minutos o texto
    en español/inglés. Devuelve (duracion_iso, es_valido).
    """
    if val is None:
        return None, True

    if isinstance(val, (int, float)):
        if val < 0:
            return None, False
        return format_iso_duration_minutes(int(val)), True

    val_str = str(val).strip()
    if not val_str:
        return None, True

    if ISO_DURATION_REGEX.match(val_str):
        return val_str, True

    clean = val_str.lower().replace(",", ".")

    if "-" in clean:
        return None, False

    m_weeks = re.search(r"(\d+)\s*(?:semanas?|weeks?|sem|w)\b", clean)
    m_days = re.search(r"(\d+(?:\.\d+)?)\s*(?:d[ií]as?|days?|d)\b", clean)
    m_hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:horas?|hours?|hrs?|h)\b", clean)
    m_mins = re.search(r"(\d+)\s*(?:minutos?|minutes?|mins?|m)\b", clean)

    if m_days and not (m_hours or m_mins or m_weeks):
        return f"P{int(float(m_days.group(1)))}D", True

    if m_weeks and not (m_days or m_hours or m_mins):
        return f"P{int(m_weeks.group(1))}W", True

    if m_hours and m_mins:
        hours = float(m_hours.group(1))
        minutes = int(m_mins.group(1))
        total = int(hours * 60) + minutes
        return format_iso_duration_minutes(total), True
    elif m_hours:
        hours = float(m_hours.group(1))
        total = int(round(hours * 60))
        return format_iso_duration_minutes(total), True
    elif m_mins:
        total = int(m_mins.group(1))
        return format_iso_duration_minutes(total), True

    m_num = re.match(r"^\d+$", clean)
    if m_num:
        return format_iso_duration_minutes(int(clean)), True

    return None, False


# ==============================================================================
# Helper de limpieza y acotado factual de descripciones
# ==============================================================================
def clean_and_truncate_description(raw_desc: str | None, max_chars: int = 350) -> str | None:
    """
    Limpia etiquetas HTML, colapsa espacios en blanco y trunca limpiamente a
    <= max_chars (respetando fin de oración o límite de palabra con '…').
    """
    if not raw_desc or not raw_desc.strip():
        return None

    text = html.unescape(raw_desc)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return None

    if len(text) <= max_chars:
        return text

    candidate = text[: max_chars - 1]

    m_sentences = list(re.finditer(r"[.!?](?:\s|$)", candidate))
    if m_sentences:
        last_s = m_sentences[-1]
        if last_s.end() >= 160:
            return candidate[: last_s.end()].strip()

    last_space = candidate.rfind(" ")
    if last_space > 0:
        return candidate[:last_space].rstrip() + "…"

    return candidate + "…"


# ==============================================================================
# Helper de cálculo de content_hash SHA-256
# ==============================================================================
def compute_course_content_hash(
    name: str,
    provider: str | None,
    authors: list[str] | None,
    category: str | None,
    keywords: list[str] | None,
    access_type: AccessType,
    educational_level: str | None,
    time_required: str | None,
    in_language: str | None,
    description: str | None,
    course_prerequisites: list[str] | None,
) -> str:
    """
    Genera un hash SHA-256 determinista a partir de los campos descriptivos y
    pedagógicos normalizados. Los arrays se ordenan alfabéticamente.
    """
    payload = {
        "access_type": access_type.value if access_type else "",
        "authors": sorted(authors, key=str.lower) if authors else [],
        "category": category or "",
        "course_prerequisites": sorted(course_prerequisites, key=str.lower) if course_prerequisites else [],
        "description": description or "",
        "educational_level": educational_level or "",
        "in_language": in_language or "",
        "keywords": sorted(keywords, key=str.lower) if keywords else [],
        "name": name.strip() if name else "",
        "provider": provider.strip() if provider else "",
        "time_required": time_required or "",
    }
    raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


# ==============================================================================
# Modelo Principal Course (Pydantic v2 Estático)
# ==============================================================================
class Course(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Identidad y URLs
    name: str = Field(description="Nombre oficial del curso")
    url: str = Field(description="URL original capturada del proveedor")
    canonical_url: str = Field(default="", description="URL canónica y normalizada (calculada)")
    content_hash: str = Field(default="", description="Hash SHA-256 de los contenidos descriptivos")

    # Metadatos descriptivos
    description: str | None = Field(default=None, description="Resumen descriptivo limpio (máx ~350 chars)")
    provider: str | None = Field(default=None, description="Nombre de la institución o plataforma proveedora")
    authors: list[str] | None = Field(default=None, description="Lista de autores o instructores")
    category: str | None = Field(default=None, description="Categoría CINE-F 2013 / DigComp 2.2 controlada")
    keywords: list[str] | None = Field(default=None, description="Etiquetas técnicas originales del proveedor")

    # Rigor pedagógico y filtro anti-pago
    access_type: AccessType = Field(
        default=AccessType.free_no_certificate,
        description="Modalidad de acceso gratuito y certificación",
    )
    educational_level: str | None = Field(
        default=None,
        description="Nivel educativo normalizado (Principiante, Intermedio, Avanzado)",
    )
    time_required: str | None = Field(default=None, description="Duración normalizada a ISO 8601 (ej. PT2H)")
    in_language: str | None = Field(default=None, description="Código ISO 639-1 del idioma (ej. 'es', 'en')")
    course_prerequisites: list[str] | None = Field(default=None, description="Requisitos previos de conocimiento")
    is_accessible_for_free: bool = Field(default=True, description="Debe ser siempre True; cursos de pago se descartan")

    # Recursos adicionales y ciclo de vida
    image: str | None = Field(default=None, description="URL de imagen o miniatura del curso")
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fecha y hora UTC de extracción",
    )
    needs_review: bool = Field(default=False, description="Flag de triaje automático para revisión manual")
    review_notes: list[str] = Field(
        default_factory=list,
        description="Motivos específicos acumulados si requiere revisión",
    )

    @property
    def educational_credential_awarded(self) -> str:
        """Etiqueta oficial en español para schema:educationalCredentialAwarded."""
        return self.access_type.credential_label_es

    # --------------------------------------------------------------------------
    # Validador de Modelo (Normalización y Consistencia de Negocio)
    # --------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_and_normalize(self) -> Course:
        # 1. Filtro estricto anti-pago
        if not self.is_accessible_for_free:
            raise ValueError(
                "El curso no es accesible gratuitamente (is_accessible_for_free=False). "
                "Descartado por la regla anti-pago de Cursodex."
            )

        # 2. Sanitización de textos y listas (HTML unescape, etiquetas, espacios)
        clean_name = clean_text_field(self.name)
        if not clean_name:
            raise ValueError("El nombre del curso no puede estar vacío.")

        clean_provider = clean_text_field(self.provider)
        clean_authors = clean_and_dedup_list(self.authors)
        clean_keywords = clean_and_dedup_list(self.keywords)
        clean_prereqs = clean_and_dedup_list(self.course_prerequisites)

        # 3. Canonización de URL y anti-redirección de portada
        raw_to_clean = self.url or self.canonical_url
        clean_url = canonicalize_url(raw_to_clean)

        # 4. Limpieza y validación de imagen
        clean_img: str | None = None
        if self.image and str(self.image).strip():
            resolved_img = urllib.parse.urljoin(clean_url, str(self.image).strip())
            parsed_img = urllib.parse.urlsplit(resolved_img)
            if parsed_img.scheme in ("http", "https") and parsed_img.netloc:
                clean_img = resolved_img

        # 5. Normalización de fecha UTC
        dt = self.last_seen_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)

        # 6. Limpieza y acotado factual de descripción
        clean_desc = self.description
        if clean_desc:
            clean_desc = clean_and_truncate_description(clean_desc)

        # 7. Normalización de categoría (mappings/vocab_map.yml)
        clean_cat = resolve_category(
            category_hint=self.category,
            keywords=clean_keywords,
            title=clean_name,
        )

        # 8. Normalización de nivel educativo
        clean_level = self.educational_level
        if clean_level:
            clean_level = resolve_educational_level(clean_level)

        # 9. Normalización de idioma
        clean_lang = self.in_language
        if clean_lang:
            clean_lang = resolve_language(clean_lang)

        # 10. Normalización de duración a ISO 8601
        notes = clean_and_dedup_list(self.review_notes) or []
        clean_dur = self.time_required
        if clean_dur is not None:
            norm_dur, dur_valid = parse_and_normalize_duration(clean_dur)
            if dur_valid:
                clean_dur = norm_dur
            else:
                notes.append(f"Duración no interpretable como ISO 8601: '{clean_dur}'")
                clean_dur = None

        # 11. Triaje de calidad automático (needs_review)
        if not clean_desc or len(clean_desc) < 30:
            notes.append("Descripción ausente o demasiado corta (< 30 caracteres)")

        if not clean_lang:
            notes.append("Idioma no identificado")

        if clean_cat == "Pendiente_Categoria":
            notes.append("Categoría no identificada en vocabulario controlado (Pendiente_Categoria)")

        # Desduplicar y ordenar notas de revisión
        dedup_notes = clean_and_dedup_list(notes) or []

        # 12. Cálculo del hash determinista de contenido
        calc_hash = compute_course_content_hash(
            name=clean_name,
            provider=clean_provider,
            authors=clean_authors,
            category=clean_cat,
            keywords=clean_keywords,
            access_type=self.access_type,
            educational_level=clean_level,
            time_required=clean_dur,
            in_language=clean_lang,
            description=clean_desc,
            course_prerequisites=clean_prereqs,
        )

        # Asignar campos normalizados directamente
        object.__setattr__(self, "name", clean_name)
        object.__setattr__(self, "provider", clean_provider)
        object.__setattr__(self, "authors", clean_authors)
        object.__setattr__(self, "keywords", clean_keywords)
        object.__setattr__(self, "course_prerequisites", clean_prereqs)
        object.__setattr__(self, "canonical_url", clean_url)
        object.__setattr__(self, "image", clean_img)
        object.__setattr__(self, "last_seen_at", dt)
        object.__setattr__(self, "description", clean_desc)
        object.__setattr__(self, "category", clean_cat)
        object.__setattr__(self, "educational_level", clean_level)
        object.__setattr__(self, "in_language", clean_lang)
        object.__setattr__(self, "time_required", clean_dur)
        object.__setattr__(self, "review_notes", dedup_notes)
        object.__setattr__(self, "needs_review", len(dedup_notes) > 0)
        object.__setattr__(self, "content_hash", calc_hash)

        return self
