from __future__ import annotations

import csv
import gzip
import io
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

import cli
from config import config
from core.crawler import Crawler
from core.drivers import SitemapJsonLdDriver
from core.exceptions import (
    HTTPStatusError,
    NetworkError,
    QualityGateError,
    UpstreamFormatError,
)
from core.manifest import ProviderDefinition, StrategyDefinition
from core.quality import BatchQualityGate
from core.strategy import StrategyRunner
from exporters.csv_exporter import CSVExporter, course_to_csv_row
from exporters.jsonld_exporter import JSONLDExporter, course_to_omeka_jsonld
from schemas.models import Course, get_vocab_map

_RUNNER = CliRunner()
_PROVIDER = ProviderDefinition(
    id="audit",
    name="Audit Learning",
    base_url="https://learn.microsoft.com/catalog",
    allowed_hosts=["learn.microsoft.com"],
    default_language="en",
    recommended_limit=10,
    requires_browser=False,
    datacenter_waf_sensitive=False,
    strategies=[
        StrategyDefinition(driver="audit_first"),
        StrategyDefinition(driver="audit_second"),
    ],
)
_SITEMAP_PROVIDER = ProviderDefinition(
    id="audit_sitemap",
    name="Audit Learning",
    base_url="https://courses.example/catalog",
    allowed_hosts=["courses.example"],
    default_language="en",
    recommended_limit=10,
    requires_browser=False,
    datacenter_waf_sensitive=False,
    strategies=[StrategyDefinition(driver="sitemap_jsonld")],
)


def _course(
    name: str = "Audit course",
    *,
    url: str = "https://learn.microsoft.com/training/courses/audit",
    description: str | None = "A sufficiently detailed course description for testing.",
    category: str | None = None,
) -> Course:
    return Course(
        name=name,
        url=url,
        description=description,
        provider=_PROVIDER.name,
        in_language="en",
        category=category,
    )


class _FakeCrawler:
    def __init__(
        self,
        sitemap_payloads: dict[str, bytes],
        pages: dict[str, str] | None = None,
    ) -> None:
        self.sitemap_payloads = sitemap_payloads
        self.pages = pages or {}
        self.byte_requests: list[str] = []
        self.page_requests: list[str] = []

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        del kwargs
        self.byte_requests.append(url)
        return self.sitemap_payloads[url]

    def get(self, url: str, **kwargs: Any) -> str:
        del kwargs
        self.page_requests.append(url)
        return self.pages[url]


def _jsonld_page(
    *,
    url: str,
    name: str,
    extra: dict[str, Any] | None = None,
) -> str:
    course: dict[str, Any] = {
        "@type": ["Course", "LearningResource"],
        "name": name,
        "url": url,
        "description": "A complete course description with useful learning details.",
        "inLanguage": "en",
        "isAccessibleForFree": True,
    }
    course.update(extra or {})
    return (
        '<script type="application/ld+json">'
        + json.dumps({"@graph": [course]})
        + "</script>"
    )


def test_jsonld_export_contract_and_category_visibility() -> None:
    resolved = _course(category="Redes, Cloud y Ciberseguridad")
    item = course_to_omeka_jsonld(resolved)

    assert item["@context"] == {
        "o": "http://omeka.org/s/vocabs/o#",
        "schema": "https://schema.org/",
        "dcterms": "http://purl.org/dc/terms/",
    }
    assert item["@type"] == ["o:Item", "schema:Course"]
    for property_name in (
        "schema:name",
        "schema:url",
        "schema:provider",
        "schema:inLanguage",
        "schema:isAccessibleForFree",
        "_cursodex_meta",
    ):
        assert property_name in item
    assert item["_cursodex_meta"]["canonical_url"] == resolved.canonical_url
    assert item["_cursodex_meta"]["category"] == "Redes, Cloud y Ciberseguridad"
    assert item["schema:about"][0]["@value"] == "Redes, Cloud y Ciberseguridad"

    unresolved = _course(
        "Programa Impulsa 2026",
        url="https://learn.microsoft.com/training/courses/impulsa",
        category="Pendiente_Categoria",
    )
    unresolved_item = course_to_omeka_jsonld(unresolved)
    assert "schema:about" not in unresolved_item
    assert "dcterms:subject" not in unresolved_item
    assert unresolved_item["_cursodex_meta"]["category"] == "Pendiente_Categoria"


def test_jsonld_export_is_byte_deterministic_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    course = _course()
    outputs: list[bytes] = []
    for _ in range(2):
        destination = io.StringIO()
        monkeypatch.setattr(sys, "stdout", destination)
        JSONLDExporter().export([course, course.model_copy()], "-")
        outputs.append(destination.getvalue().encode("utf-8"))

    assert outputs[0] == outputs[1]
    assert len(json.loads(outputs[0])) == 1


def test_csv_export_cleans_control_characters_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    course = _course("Curso\x00\n de prueba", description="Descripción\x00 corta")
    row = course_to_csv_row(course)
    assert all("\x00" not in value for value in row.values() if isinstance(value, str))

    destination = io.StringIO()
    monkeypatch.setattr(sys, "stdout", destination)
    CSVExporter().export([course, course.model_copy()], "-")
    records = list(csv.DictReader(io.StringIO(destination.getvalue())))
    assert len(records) == 1
    assert records[0]["schema:name"] == "Curso de prueba"
    assert "\x00" not in destination.getvalue()


def test_quality_gate_keeps_exactly_half_invalid_and_deduplicates() -> None:
    courses = [
        _course("Valid one", url="https://learn.microsoft.com/training/courses/one"),
        _course("404 Not Found", url="https://learn.microsoft.com/training/courses/two"),
        _course("Valid three", url="https://learn.microsoft.com/training/courses/three"),
        _course("403 Forbidden", url="https://learn.microsoft.com/training/courses/four"),
    ]

    valid = BatchQualityGate.validate(courses, _PROVIDER)
    assert [course.name for course in valid] == ["Valid one", "Valid three"]

    deduplicated = BatchQualityGate.validate(
        [_course(), _course()],
        _PROVIDER,
    )
    assert len(deduplicated) == 1


@pytest.mark.parametrize(
    "invalid_courses",
    [
        [
            _course("Good one", url="https://learn.microsoft.com/training/courses/1"),
            _course("Good two", url="https://learn.microsoft.com/training/courses/2"),
            _course("404 Not Found", url="https://learn.microsoft.com/training/courses/3"),
            _course("Just a moment...", url="https://learn.microsoft.com/training/courses/4"),
            _course("403 Forbidden", url="https://learn.microsoft.com/training/courses/5"),
        ],
        [_course("Attention Required! | Cloudflare")],
    ],
)
def test_quality_gate_rejects_over_half_invalid_or_single_invalid(
    invalid_courses: list[Course],
) -> None:
    with pytest.raises(QualityGateError):
        BatchQualityGate.validate(invalid_courses, _PROVIDER)


@pytest.mark.parametrize(
    "url",
    [
        "http://learn.microsoft.com/training/courses/http",
        "https://evillearn.microsoft.com/training/courses/trap",
        "https://learn.microsoft.com.attacker.org/training/courses/trap",
        "https://learn.microsoft.com/",
        "https://learn.microsoft.com/login",
        "https://user:pass@learn.microsoft.com/training/courses/credentials",
        "https://127.0.0.1/training/courses/private",
    ],
)
def test_quality_gate_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises((QualityGateError, ValueError)):
        BatchQualityGate.validate(
            [
                {
                    "name": "URL test",
                    "url": url,
                    "provider": _PROVIDER.name,
                    "in_language": "en",
                }
            ],
            _PROVIDER,
        )


@pytest.mark.parametrize(
    "title",
    [
        "Just a moment...",
        "403 Forbidden",
        "Attention Required! | Cloudflare",
        "404 Not Found",
    ],
)
def test_quality_gate_rejects_block_page_titles(title: str) -> None:
    with pytest.raises(QualityGateError):
        BatchQualityGate.validate([_course(title)], _PROVIDER)


@pytest.mark.parametrize("description", ["", "Curso corto"])
def test_quality_gate_keeps_missing_or_short_descriptions(description: str) -> None:
    course = _course(description=description)
    result = BatchQualityGate.validate([course], _PROVIDER)
    assert result == [course]


@pytest.mark.parametrize("url", ["http://courses.example/catalog", "https://user@courses.example/catalog"])
def test_crawler_rejects_non_https_or_credential_urls_before_request(url: str) -> None:
    with pytest.raises(NetworkError):
        Crawler.validate_safe_url(url, ["courses.example"])


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/catalog",
        "https://service.local/catalog",
        "https://127.0.0.1/catalog",
        "https://[::1]/catalog",
        "https://169.254.10.20/catalog",
    ],
)
def test_crawler_rejects_local_and_non_public_ip_destinations(url: str) -> None:
    with pytest.raises(NetworkError):
        Crawler.validate_safe_url(url)


def test_crawler_rejects_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.0.0.8", 443),
            )
        ],
    )
    with pytest.raises(NetworkError, match="non-public IP"):
        Crawler.validate_safe_url("https://courses.example/catalog")


def test_crawler_blocks_external_and_login_redirects_before_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    initial_url = "https://courses.example/course/1"
    external_url = "https://attacker.example/login"
    login_url = "https://courses.example/login"
    with respx.mock:
        external_route = respx.get(initial_url).mock(
            return_value=httpx.Response(302, headers={"location": external_url})
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(NetworkError):
                crawler.get(
                    initial_url,
                    allowed_hosts=["courses.example"],
                    reject_login_path=True,
                )
        assert external_route.call_count == 1
        assert [call.request.url.host for call in respx.calls] == ["courses.example"]

    with respx.mock:
        login_route = respx.get(initial_url).mock(
            return_value=httpx.Response(302, headers={"location": login_url})
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(NetworkError, match="Login URLs"):
                crawler.get(
                    initial_url,
                    allowed_hosts=["courses.example"],
                    reject_login_path=True,
                )
        assert login_route.call_count == 1


@pytest.mark.parametrize("status_code", [401, 403, 404, 410])
def test_response_guard_makes_one_request_for_definitive_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(status_code))
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(HTTPStatusError):
                crawler.get(url, expected_format="json")
    assert route.call_count == 1


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ({"cf-mitigated": "challenge"}, "blocked"),
        ({}, "<html><title>Just a moment...</title></html>"),
    ],
)
def test_response_guard_makes_one_request_for_503_challenges(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    body: str,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(503, text=body, headers=headers)
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(HTTPStatusError):
                crawler.get(url, expected_format="json")
    assert route.call_count == 1


@pytest.mark.parametrize("status_code", [502, 503])
def test_response_guard_retries_transient_server_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    monkeypatch.setattr("core.crawler.time.sleep", lambda _: None)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(status_code, text="temporary failure"),
                httpx.Response(200, json={"courses": []}),
            ]
        )
        with Crawler() as crawler:
            crawler.delay = 0
            assert crawler.get(url, expected_format="json") == '{"courses":[]}'
    assert route.call_count == 2


def test_crawler_enforces_download_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.xml"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, content=b"12345"))
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(UpstreamFormatError, match="4-byte limit"):
                crawler.get_bytes(url, max_bytes=4)


def test_crawler_decodes_content_encoding_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    compressed = gzip.compress(b'{"courses":[]}')
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(
                200,
                content=compressed,
                headers={"content-encoding": "gzip", "content-type": "application/json"},
            )
        )
        with Crawler() as crawler:
            crawler.delay = 0
            assert crawler.get(url, expected_format="json") == '{"courses":[]}'
    assert route.call_count == 1


def test_strategy_runner_falls_back_after_html_masquerades_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                text="<!DOCTYPE html><html>Mantenimiento",
            )
        )

        def fake_driver(
            driver: str,
            adapter: object,
            target_url: str,
            provider: ProviderDefinition,
            params: dict[str, Any],
            limit: int,
            enable_modules: bool,
        ) -> list[Course]:
            del adapter, provider, params, limit, enable_modules
            if driver == "audit_first":
                with Crawler() as crawler:
                    crawler.delay = 0
                    crawler.get(target_url, expected_format="json")
            return [_course(url="https://learn.microsoft.com/training/courses/fallback")]

        monkeypatch.setattr("core.strategy.run_driver", fake_driver)
        courses = StrategyRunner({"audit": _PROVIDER}).run("audit", object(), url)

    assert [course.name for course in courses] == ["Audit course"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Programación estadística en lenguaje R", "Programación y Desarrollo de Software"),
        ("Fundamentos del lenguaje C++ y algoritmos", "Programación y Desarrollo de Software"),
        ("Inglés B2 para entornos profesionales", "Idiomas"),
        ("Arquitectura de microservicios en la nube", "Redes, Cloud y Ciberseguridad"),
        ("Seguridad en redes TCP/IP y firewalls", "Redes, Cloud y Ciberseguridad"),
        ("Contabilidad financiera y presupuestos", "Administración de Empresas y Derecho"),
        ("Historia del arte renacentista", "Artes, Diseño y Humanidades"),
        ("Primeros auxilios y nutrición clínica", "Salud y Bienestar"),
        ("Programa Impulsa 2026", "Pendiente_Categoria"),
        ("Módulo 1: Conceptos generales", "Pendiente_Categoria"),
        ("Taller introductorio nivel básico", "Pendiente_Categoria"),
        ("Marketing de contenidos y publicidad digital", "Marketing Digital y Comercio Electrónico"),
        ("Química orgánica y laboratorio", "Ciencias Naturales, Matemáticas y Estadística"),
        ("Didáctica y pedagogía para docentes", "Educación y Pedagogía"),
        ("Operaciones de turismo y hostelería", "Hostelería, Turismo y Servicios"),
        ("Energías renovables y economía circular", "Sostenibilidad, Medio Ambiente y Agroalimentación"),
    ],
)
def test_category_adversarial_matrix(title: str, expected: str) -> None:
    course = Course(
        name=title,
        url="https://courses.example/course/audit",
        description=None,
        in_language="es",
    )
    assert course.category == expected


def test_taxonomy_lists_exactly_the_17_canonical_categories() -> None:
    taxonomy_path = Path(__file__).resolve().parents[1] / "docs" / "TAXONOMY.md"
    taxonomy = taxonomy_path.read_text(encoding="utf-8")
    sections = re.findall(r"(?m)^### \d{2}\. (.+)$", taxonomy)
    canonicals = [entry["canonical"] for entry in get_vocab_map()["categories"]]
    assert sections == canonicals


def test_sitemap_driver_bounded_gzip_and_safe_xml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sitemap_url = "https://courses.example/sitemap.xml.gz"
    xml_payload = b"<urlset></urlset>"
    crawler = _FakeCrawler({sitemap_url: gzip.compress(xml_payload)})
    driver = SitemapJsonLdDriver(
        crawler,  # type: ignore[arg-type]
        _SITEMAP_PROVIDER,
        {"sitemap_url": sitemap_url},
    )
    assert driver._sitemap_urls(sitemap_url) == []

    monkeypatch.setattr("core.drivers.MAX_RESPONSE_BYTES", 32)
    expanded = b"<urlset>" + (b" " * 64) + b"</urlset>"
    oversized_crawler = _FakeCrawler({sitemap_url: gzip.compress(expanded)})
    oversized = SitemapJsonLdDriver(
        oversized_crawler,  # type: ignore[arg-type]
        _SITEMAP_PROVIDER,
        {"sitemap_url": sitemap_url},
    )
    with pytest.raises(UpstreamFormatError, match="Decompressed sitemap exceeded"):
        oversized._sitemap_urls(sitemap_url)

    dtd_url = "https://courses.example/sitemap.xml"
    dtd_crawler = _FakeCrawler(
        {dtd_url: b'<!DOCTYPE urlset [<!ENTITY x "x">]><urlset>&x;</urlset>'}
    )
    dtd_driver = SitemapJsonLdDriver(
        dtd_crawler,  # type: ignore[arg-type]
        _SITEMAP_PROVIDER,
        {"sitemap_url": dtd_url},
    )
    with pytest.raises(UpstreamFormatError):
        dtd_driver._sitemap_urls(dtd_url)


def test_sitemap_index_stops_cycles_and_skips_foreign_hosts() -> None:
    root_url = "https://courses.example/sitemap.xml"
    foreign_url = "https://attacker.example/sitemap.xml"
    index = (
        "<sitemapindex><sitemap><loc>"
        + root_url
        + "</loc></sitemap><sitemap><loc>"
        + foreign_url
        + "</loc></sitemap></sitemapindex>"
    )
    crawler = _FakeCrawler({root_url: index.encode("utf-8")})
    driver = SitemapJsonLdDriver(
        crawler,  # type: ignore[arg-type]
        _SITEMAP_PROVIDER,
        {"sitemap_url": root_url},
    )

    assert driver._sitemap_urls(root_url) == []
    assert crawler.byte_requests == [root_url]


def test_sitemap_driver_skips_bad_jsonld_and_paid_courses_before_limit() -> None:
    sitemap_url = "https://courses.example/sitemap.xml"
    paid_free_flag_url = "https://courses.example/courses/paid-free-flag"
    paid_offer_url = "https://courses.example/courses/paid-offer"
    free_url = "https://courses.example/courses/free"
    extra_free_url = "https://courses.example/courses/extra"
    sitemap = (
        "<urlset>"
        + "".join(
            f"<url><loc>{url}</loc></url>"
            for url in (paid_free_flag_url, paid_offer_url, free_url, extra_free_url)
        )
        + "</urlset>"
    )
    pages = {
        paid_free_flag_url: _jsonld_page(
            url=paid_free_flag_url,
            name="Paid course with false free flag",
            extra={"isAccessibleForFree": False},
        ),
        paid_offer_url: _jsonld_page(
            url=paid_offer_url,
            name="Paid offer despite free flag",
            extra={"isAccessibleForFree": True, "offers": {"price": "12.00"}},
        ),
        free_url: (
            '<script type="application/ld+json">{broken json}</script>'
            '<script type="application/ld+json">'
            + json.dumps({"@type": "WebSite", "name": "Not a course"})
            + "</script>"
            + _jsonld_page(url=free_url, name="Free course")
        ),
        extra_free_url: _jsonld_page(url=extra_free_url, name="Extra free course"),
    }
    crawler = _FakeCrawler({sitemap_url: sitemap.encode("utf-8")}, pages)
    courses = SitemapJsonLdDriver(
        crawler,  # type: ignore[arg-type]
        _SITEMAP_PROVIDER,
        {"sitemap_url": sitemap_url},
        limit=1,
    ).scrape()

    assert [course.name for course in courses] == ["Free course"]
    assert crawler.page_requests == [paid_free_flag_url, paid_offer_url, free_url]


@pytest.mark.parametrize(("exit_code", "result"), [(2, []), (0, [_course()])])
def test_cli_preserves_clean_empty_and_success_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    result: list[Course],
) -> None:
    monkeypatch.setattr(StrategyRunner, "run", lambda *args, **kwargs: result)
    response = _RUNNER.invoke(
        cli.app,
        ["run", "--provider", "ms_learn", "--output", "-", "--format", "jsonld"],
    )
    assert response.exit_code == exit_code
    if exit_code == 0:
        assert len(json.loads(response.stdout)) == 1
    else:
        assert json.loads(response.stdout) == []


def test_cli_maps_quality_gate_failure_to_exit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_quality_gate(*args: Any, **kwargs: Any) -> list[Course]:
        del args, kwargs
        raise QualityGateError("invalid batch")

    monkeypatch.setattr(StrategyRunner, "run", fail_quality_gate)
    response = _RUNNER.invoke(
        cli.app,
        ["run", "--provider", "ms_learn", "--output", "-", "--format", "jsonld"],
    )
    assert response.exit_code == 1


def test_cli_deduplicates_before_export_and_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    course = _course(url="https://learn.microsoft.com/training/courses/duplicate")
    monkeypatch.setattr(StrategyRunner, "run", lambda *args, **kwargs: [course, course.model_copy()])
    response = _RUNNER.invoke(
        cli.app,
        ["run", "--provider", "ms_learn", "--output", "-", "--format", "jsonld"],
    )

    assert response.exit_code == 0
    assert len(json.loads(response.stdout)) == 1
    assert '"courses_extracted": 1' in response.stderr
