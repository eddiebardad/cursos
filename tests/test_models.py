"""
tests/test_models.py
==============================================================================
Suite exhaustiva de pruebas unitarias para el modelo Course (Pydantic v2).

Verifica:
1. Canonización de URLs (limpieza de tracking, orden de query params, anti-redirección de portada).
2. Prevención de colisiones con sinónimos cortos (límites de palabra en regex).
3. Normalización de duraciones a ISO 8601 (decimales, minutos, semanas, texto ambiguo).
4. Determinismo de content_hash (inclusión de autores/proveedor, exclusión de timestamps).
5. Enum AccessType y su etiqueta oficial en español.
6. Filtro anti-pago (rechazo con ValidationError si is_accessible_for_free=False).
7. Limpieza y acotado factual de descripciones (<= 350 chars con elipsis).
8. Criterios refinados de triaje automático (needs_review).
9. Orden de especificidad en la resolución de categorías CINE-F 2013 / DigComp 2.2.
==============================================================================
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from schemas.models import (
    AccessType,
    Course,
    canonicalize_url,
    clean_and_truncate_description,
    match_synonym_boundary,
    parse_and_normalize_duration,
)


# ==============================================================================
# 1. Pruebas de Canonización de URL
# ==============================================================================
def test_canonical_url_preserves_legitimate_params_and_strips_tracking():
    raw_url = (
        "http://ACADEMY.Hubspot.COM/courses/python-intro/?"
        "utm_source=facebook&lang=es&utm_medium=cpc&id=42&ref=partner&fbclid=XYZ123"
        "&WT.mc_id=api_CatalogApi#curriculum"
    )
    course = Course(
        name="Introducción a Python",
        url=raw_url,
        description="Aprende programación básica en Python desde cero con ejercicios prácticos.",
        in_language="es",
    )
    # 1. Forzar https
    # 2. Hostname en minúsculas
    # 3. Sin trailing slash redundante
    # 4. Parámetros de rastreo eliminados (utm_*, ref, fbclid)
    # 5. Parámetros legítimos conservados y ordenados (?id=42&lang=es)
    # 6. Sin fragmento (#curriculum)
    assert course.canonical_url == "https://academy.hubspot.com/courses/python-intro?id=42&lang=es"
    assert canonicalize_url(raw_url) == "https://academy.hubspot.com/courses/python-intro?id=42&lang=es"


def test_canonical_url_rejects_root_url_redirection():
    """Trampa de redirección a portada (ELIXIR TeSS): debe lanzar error si no hay path."""
    with pytest.raises(ValidationError) as exc_info:
        Course(
            name="Curso Redirigido",
            url="https://academy.hubspot.com/",
            description="Descripción genérica de un curso cuya URL expiró.",
            in_language="es",
        )
    assert "carece de ruta de recurso" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info2:
        Course(
            name="Curso Redirigido Sin Slash",
            url="https://learn.microsoft.com",
            description="Descripción genérica de un curso sin ruta.",
            in_language="es",
        )
    assert "carece de ruta de recurso" in str(exc_info2.value)


# ==============================================================================
# 2. Pruebas de Límites de Palabra y No-Colisión de Sinónimos Cortos
# ==============================================================================
def test_synonym_boundary_short_words_no_false_positives():
    """
    Sinónimos como 'ia', 'it', 'ai', 'ti', 'r', 'c' NO deben hacer match dentro
    de palabras como 'historia', 'literatura' o 'arquitectura'.
    """
    text = "Historia de la literatura italiana"
    assert not match_synonym_boundary("ia", text)
    assert not match_synonym_boundary("it", text)
    assert not match_synonym_boundary("ai", text)
    assert match_synonym_boundary("historia", text)
    assert match_synonym_boundary("literatura", text)

    course = Course(
        name="Historia de la literatura italiana",
        url="https://ejemplo.com/cursos/literatura-italiana",
        description="Un recorrido completo por los grandes autores de la literatura de Italia.",
        in_language="es",
    )
    assert course.category == "Artes y Humanidades"
    assert course.category != "Ciencia de Datos e Inteligencia Artificial"
    assert course.category != "Tecnologías de la Información y la Comunicación (General)"


def test_synonym_boundary_short_words_positive_match():
    """Cuando 'IA' o 'AI' es una palabra independiente, sí debe coincidir."""
    text = "Introducción a la IA aplicada a negocios"
    assert match_synonym_boundary("ia", text)

    course = Course(
        name="Introducción a la IA aplicada",
        url="https://ejemplo.com/cursos/ia-aplicada",
        description="Fundamentos prácticos de inteligencia artificial y redes neuronales.",
        in_language="es",
    )
    assert course.category == "Ciencia de Datos e Inteligencia Artificial"


def test_synonym_boundary_accents_and_symbols():
    """Confirma que tildes, ñ y símbolos técnicos (+, #) se manejan correctamente sin falsos separadores."""
    assert match_synonym_boundary("programacion", "Curso avanzado de programación en la nube")
    assert match_synonym_boundary("programación", "Curso de programacion estructurada")
    assert match_synonym_boundary("espanol", "Material didáctico en español neutro")
    assert match_synonym_boundary("español", "Material didactico en espanol")
    assert match_synonym_boundary("c++", "Aprende c++ y estructuras de datos")
    assert match_synonym_boundary("c#", "Desarrollo empresarial con c# y .net")


# ==============================================================================
# 3. Pruebas de Normalización de Duraciones (ISO 8601)
# ==============================================================================
def test_duration_normalization_formats():
    assert parse_and_normalize_duration(90) == ("PT1H30M", True)
    assert parse_and_normalize_duration("90 min") == ("PT1H30M", True)
    assert parse_and_normalize_duration("90 minutos") == ("PT1H30M", True)
    assert parse_and_normalize_duration("1.5 horas") == ("PT1H30M", True)
    assert parse_and_normalize_duration("1,5 h") == ("PT1H30M", True)
    assert parse_and_normalize_duration("2 horas 30 min") == ("PT2H30M", True)
    assert parse_and_normalize_duration("PT45M") == ("PT45M", True)
    assert parse_and_normalize_duration("PT2H") == ("PT2H", True)
    assert parse_and_normalize_duration("4 semanas") == ("P4W", True)


def test_duration_ambiguous_text_triggers_review():
    course = Course(
        name="Curso con duración flexible",
        url="https://ejemplo.com/cursos/flexible",
        description="Aprende a tu propio ritmo con contenidos grabados accesibles siempre.",
        in_language="es",
        time_required="A tu propio ritmo",
    )
    assert course.time_required is None
    assert course.needs_review is True
    assert any("Duración no interpretable" in note for note in course.review_notes)


# ==============================================================================
# 4. Pruebas de content_hash Determinista
# ==============================================================================
def test_content_hash_deterministic_and_excluded_fields():
    base_kwargs = {
        "name": "Machine Learning para Principiantes",
        "url": "https://learn.microsoft.com/es-es/training/paths/ml-beginners",
        "provider": "Microsoft Learn",
        "authors": ["John Doe", "Alice Smith"],
        "keywords": ["Python", "Azure", "Machine Learning"],
        "access_type": AccessType.free_with_certificate,
        "educational_level": "Principiante",
        "time_required": "PT3H",
        "in_language": "es",
        "description": "Itinerario formativo completo de introducción al aprendizaje automático.",
        "course_prerequisites": ["Conocimientos básicos de álgebra", "Fundamentos de Python"],
    }

    c1 = Course(**base_kwargs)
    c2 = Course(**base_kwargs)
    assert c1.content_hash == c2.content_hash
    assert len(c1.content_hash) == 64

    c_reordered = Course(
        **{
            **base_kwargs,
            "keywords": ["Machine Learning", "Python", "Azure"],
            "authors": ["Alice Smith", "John Doe"],
            "course_prerequisites": ["Fundamentos de Python", "Conocimientos básicos de álgebra"],
        }
    )
    assert c1.content_hash == c_reordered.content_hash

    c_timestamp = Course(
        **{
            **base_kwargs,
            "last_seen_at": datetime(2025, 1, 1, tzinfo=UTC),
            "image": "https://img.ejemplo.com/otra.png",
        }
    )
    assert c1.content_hash == c_timestamp.content_hash

    c_diff_provider = Course(**{**base_kwargs, "provider": "Otro Proveedor"})
    assert c1.content_hash != c_diff_provider.content_hash

    c_diff_author = Course(**{**base_kwargs, "authors": ["John Doe", "Bob Marley"]})
    assert c1.content_hash != c_diff_author.content_hash


# ==============================================================================
# 5. Pruebas del Enum AccessType y su Etiqueta Oficial
# ==============================================================================
def test_access_type_enum_and_spanish_labels():
    c_cert = Course(
        name="Curso con Certificado",
        url="https://ejemplo.com/cursos/cert",
        description="Curso gratuito oficial con emisión de certificado de finalización.",
        in_language="es",
        access_type=AccessType.free_with_certificate,
    )
    assert c_cert.access_type == AccessType.free_with_certificate
    assert c_cert.educational_credential_awarded == "Certificado gratuito"

    c_audit = Course(
        name="Curso con Certificado de Pago",
        url="https://ejemplo.com/cursos/audit",
        description="Materiales gratuitos para auditar, examen de pago opcional.",
        in_language="es",
        access_type=AccessType.free_audit_paid_certificate,
    )
    assert c_audit.access_type == AccessType.free_audit_paid_certificate
    assert c_audit.educational_credential_awarded == "Acceso gratuito (certificado de pago)"

    c_none = Course(
        name="Curso sin Certificado",
        url="https://ejemplo.com/cursos/nocert",
        description="Curso libre sin emisión de certificado ni acreditación.",
        in_language="es",
        access_type=AccessType.free_no_certificate,
    )
    assert c_none.access_type == AccessType.free_no_certificate
    assert c_none.educational_credential_awarded == "Curso gratuito (sin certificado)"


# ==============================================================================
# 6. Filtro Anti-Pago (Rechazo de Cursos de Pago)
# ==============================================================================
def test_filter_anti_payment_rejects_paid_courses():
    with pytest.raises(ValidationError) as exc_info:
        Course(
            name="Curso de Pago No Permitido",
            url="https://ejemplo.com/cursos/paid",
            description="Curso con coste de suscripción mensual obligatoria.",
            is_accessible_for_free=False,
        )
    assert "El curso no es accesible gratuitamente" in str(exc_info.value)


# ==============================================================================
# 7. Limpieza y Acotado Factual de Descripción (<= 350 caracteres)
# ==============================================================================
def test_description_cleaning_and_truncation():
    raw_html = (
        "<p>Aprende <strong>desarrollo web moderno</strong> con &aacute;giles m&eacute;todos.</p>\n"
        "<p>Descubre HTML5, CSS3, JavaScript y TypeScript paso a paso. "
        "En este curso aprenderás a diseñar arquitecturas escalables, escribir pruebas unitarias, "
        "gestionar despliegues continuos en contenedores y construir interfaces accesibles "
        "con los más altos estándares de calidad del software y diseño centrado en el usuario.</p>"
    )
    cleaned = clean_and_truncate_description(raw_html, max_chars=350)
    assert cleaned is not None
    assert "<p>" not in cleaned
    assert "<strong>" not in cleaned
    assert "&aacute;" not in cleaned
    assert "ágiles" in cleaned
    assert len(cleaned) <= 350
    assert cleaned.endswith("…") or cleaned.endswith(".")


# ==============================================================================
# 8. Criterios Refinados de Triaje de Calidad (needs_review)
# ==============================================================================
def test_needs_review_conditions():
    c_short_desc = Course(
        name="Curso con descripción corta",
        url="https://ejemplo.com/cursos/short",
        description="Demasiado corta.",
        in_language="es",
    )
    assert c_short_desc.needs_review is True
    assert any("Descripción ausente o demasiado corta" in n for n in c_short_desc.review_notes)

    c_no_lang = Course(
        name="Curso sin idioma",
        url="https://ejemplo.com/cursos/nolang",
        description="Descripción suficientemente larga para pasar la validación mínima.",
        in_language=None,
    )
    assert c_no_lang.needs_review is True
    assert any("Idioma no identificado" in n for n in c_no_lang.review_notes)

    c_unmapped_cat = Course(
        name="XyZzz 9991283",
        url="https://ejemplo.com/cursos/xyz",
        description="Descripción suficientemente extensa sin ninguna pista temática conocida.",
        in_language="es",
        category="PalabraDesconocidaTotalmente",
    )
    assert c_unmapped_cat.category == "Pendiente_Categoria"
    assert c_unmapped_cat.needs_review is True
    assert any("Categoría no identificada" in n for n in c_unmapped_cat.review_notes)

    c_valid_without_level = Course(
        name="Aprende Criptografía Práctica",
        url="https://ejemplo.com/cursos/crypto",
        description="Fundamentos de cifrado simétrico y asimétrico para ingenieros de software.",
        in_language="es",
        educational_level=None,
    )
    assert c_valid_without_level.category == "Redes, Cloud y Ciberseguridad"
    assert c_valid_without_level.needs_review is False
    assert len(c_valid_without_level.review_notes) == 0


# ==============================================================================
# 9. Orden de Especificidad en la Resolución de Categorías
# ==============================================================================
def test_category_specificity_ordering():
    c_cloud = Course(
        name="Fundamentos de Azure Cloud y Seguridad",
        url="https://ejemplo.com/cursos/azure-cloud",
        description="Curso intensivo de infraestructura en la nube y configuración de firewalls.",
        in_language="es",
    )
    assert c_cloud.category == "Redes, Cloud y Ciberseguridad"

    c_data = Course(
        name="Data Science y Machine Learning",
        url="https://ejemplo.com/cursos/data-science",
        description="Análisis de datos, minería de datos y algoritmos de clasificación en Python.",
        in_language="es",
    )
    assert c_data.category == "Ciencia de Datos e Inteligencia Artificial"

    c_tic = Course(
        name="Introducción a la Informática",
        url="https://ejemplo.com/cursos/informatica",
        description="Conceptos generales de sistemas de computación y telecomunicaciones.",
        in_language="es",
    )
    assert c_tic.category == "Tecnologías de la Información y la Comunicación (General)"


# ==============================================================================
# 10. Pruebas de Idempotencia, Puertos, Sanitización, Días e Imágenes
# ==============================================================================
def test_course_model_validate_idempotence():
    c1 = Course(
        name="Programación en Python",
        url="https://ejemplo.com/cursos/python-intro",
        provider="Universidad Virtual",
        authors=["Dra. Elena Gómez", "Ing. Carlos Ruiz"],
        description="Curso intensivo con diseño de arquitecturas escalables y pruebas unitarias.",
        in_language="es",
        category="Programación y Desarrollo de Software",
        keywords=["Python", "FastAPI"],
        access_type=AccessType.free_with_certificate,
        educational_level="Avanzado",
        time_required="PT20H",
    )
    dumped = c1.model_dump()
    c2 = Course.model_validate(dumped)

    assert c1.content_hash == c2.content_hash
    assert c1.canonical_url == c2.canonical_url
    assert c1.category == c2.category
    assert c1.needs_review == c2.needs_review
    assert c1.last_seen_at == c2.last_seen_at


def test_canonical_url_strips_ports_80_and_443():
    assert canonicalize_url("http://example.com:80/courses/intro") == "https://example.com/courses/intro"
    assert canonicalize_url("https://example.com:443/courses/intro") == "https://example.com/courses/intro"
    # Puerto no estándar se conserva
    assert canonicalize_url("https://example.com:8080/courses/intro") == "https://example.com:8080/courses/intro"


def test_image_resolution_and_validation():
    # Imagen relativa resuelta contra canonical_url
    c_rel = Course(
        name="Curso con imagen relativa",
        url="https://ejemplo.com/courses/intro",
        description="Curso con imagen en ruta relativa local.",
        in_language="es",
        image="assets/banner.png",
    )
    assert c_rel.image == "https://ejemplo.com/courses/assets/banner.png"

    # Imagen absoluta válida
    c_abs = Course(
        name="Curso con imagen absoluta",
        url="https://ejemplo.com/courses/intro",
        description="Curso con imagen alojada en CDN externo.",
        in_language="es",
        image="https://cdn.ejemplo.com/img.jpg",
    )
    assert c_abs.image == "https://cdn.ejemplo.com/img.jpg"

    # Esquema no http(s) o inválido descartado a None
    c_inv = Course(
        name="Curso con imagen inválida",
        url="https://ejemplo.com/courses/intro",
        description="Curso con esquema peligroso o no parseable.",
        in_language="es",
        image="javascript:alert(1)",
    )
    assert c_inv.image is None


def test_duration_days_and_negative_rejection():
    # Días en texto en español e inglés
    iso, valid = parse_and_normalize_duration("3 días")
    assert valid and iso == "P3D"

    iso, valid = parse_and_normalize_duration("5 days")
    assert valid and iso == "P5D"

    iso, valid = parse_and_normalize_duration("1 dia")
    assert valid and iso == "P1D"

    # Duraciones negativas rechazadas
    iso, valid = parse_and_normalize_duration(-10)
    assert not valid and iso is None

    iso, valid = parse_and_normalize_duration("-2 horas")
    assert not valid and iso is None

    iso, valid = parse_and_normalize_duration("-PT5H")
    assert not valid and iso is None


def test_utc_normalization_naive_and_aware():
    from datetime import timedelta, timezone

    # Naive datetime
    naive_dt = datetime(2026, 11, 24, 12, 0, 0)
    c_naive = Course(
        name="Curso con fecha naive",
        url="https://ejemplo.com/courses/dt-naive",
        description="Verificación de asignación de timezone UTC.",
        in_language="es",
        last_seen_at=naive_dt,
    )
    assert c_naive.last_seen_at.tzinfo == UTC
    assert c_naive.last_seen_at.hour == 12

    # Aware datetime en UTC+2
    tz_plus_2 = timezone(timedelta(hours=2))
    aware_dt = datetime(2026, 11, 24, 14, 0, 0, tzinfo=tz_plus_2)
    c_aware = Course(
        name="Curso con fecha aware",
        url="https://ejemplo.com/courses/dt-aware",
        description="Verificación de conversión a timezone UTC.",
        in_language="es",
        last_seen_at=aware_dt,
    )
    assert c_aware.last_seen_at.tzinfo == UTC
    assert c_aware.last_seen_at.hour == 12


def test_text_sanitization_and_deduplication():
    # Nombre con HTML y espacios colapsados
    c = Course(
        name="  <h1>Aprende &amp; Domina Python</h1>  ",
        url="https://ejemplo.com/courses/sanitization",
        description="Descripción válida para comprobar la sanitización de campos.",
        in_language="es",
        provider="  <b>Fundación Código</b>  ",
        authors=["Jane Doe", "jane doe", "  Jane Doe  ", "John Smith"],
        keywords=["Python", "python", "PYTHON", "FastAPI"],
        course_prerequisites=["Bases de Datos", "bases de datos", "SQL"],
    )
    assert c.name == "Aprende & Domina Python"
    assert c.provider == "Fundación Código"
    assert c.authors == ["Jane Doe", "John Smith"]
    assert c.keywords == ["Python", "FastAPI"]
    assert c.course_prerequisites == ["Bases de Datos", "SQL"]

    # Nombre vacío tras sanitización debe lanzar ValueError
    with pytest.raises(ValidationError) as exc:
        Course(
            name="   <b>   </b>  ",
            url="https://ejemplo.com/courses/empty-name",
            description="Descripción de prueba.",
            in_language="es",
        )
    assert "El nombre del curso no puede estar vacío" in str(exc.value)


def test_external_review_notes_are_cleaned_and_preserved():
    course = Course(
        name="Introducción a Python",
        url="https://example.com/cursos/python",
        description="Aprende fundamentos de Python con ejercicios prácticos.",
        in_language="es",
        review_notes=[
            "  Nota externa de <b>curaduría</b>  ",
            "Nota externa de curaduría",
            "   ",
        ],
    )

    assert course.review_notes == ["Nota externa de curaduría"]
    assert course.needs_review is True


def test_external_review_notes_are_idempotent_with_automatic_notes():
    course = Course(
        name="Curso sin categoría identificada",
        url="https://example.com/cursos/sin-categoria",
        description="Breve",
        review_notes=[" Nota externa ", "Nota externa"],
    )

    restored = Course.model_validate(course.model_dump())

    assert course.review_notes[0] == "Nota externa"
    assert len(course.review_notes) == len(set(course.review_notes))
    assert restored.review_notes == course.review_notes
    assert restored.needs_review is course.needs_review is True
    assert restored.content_hash == course.content_hash
