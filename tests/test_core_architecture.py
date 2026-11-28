from __future__ import annotations

import gzip
import json
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

import cli
from config import config
from core.crawler import Crawler
from core.drivers import (
    SitemapJsonLdDriver,
    available_drivers,
)
from core.exceptions import (
    HTTPStatusError,
    NetworkError,
    QualityGateError,
    UpstreamFormatError,
    WAFChallengeError,
)
from core.manifest import ProviderDefinition, StrategyDefinition, load_provider_manifest
from core.quality import BatchQualityGate
from core.strategy import StrategyRunner
from schemas.models import Course

runner = CliRunner()
_PROVIDER = ProviderDefinition(
    id="example",
    name="Example Learning",
    base_url="https://courses.example/catalog",
    allowed_hosts=["courses.example"],
    default_language="en",
    recommended_limit=10,
    requires_browser=False,
    datacenter_waf_sensitive=False,
    strategies=[StrategyDefinition(driver="example_first"), StrategyDefinition(driver="example_second")],
)


def _course(
    title: str = "Example course",
    *,
    url: str = "https://courses.example/course/1",
    description: str | None = "A description with enough details for this course.",
    provider: str = "Example Learning",
    language: str | None = "en",
) -> Course:
    return Course(
        name=title,
        url=url,
        description=description,
        provider=provider,
        in_language=language,
    )


def test_provider_manifest_is_valid_and_drivers_are_registered() -> None:
    manifest = load_provider_manifest()

    assert set(manifest) == {"ms_learn", "openlearn", "aprende", "netacad"}
    assert manifest["openlearn"].datacenter_waf_sensitive is True
    assert manifest["netacad"].requires_browser is True
    assert "sitemap_jsonld" in available_drivers()
    assert {
        "ms_learn_api",
        "aprende_api",
        "openlearn_sitemap",
        "openlearn_catalogue",
        "netacad_playwright",
    }.issubset(available_drivers())

    with pytest.raises(ValueError):
        ProviderDefinition.model_validate(
            {
                **_PROVIDER.model_dump(),
                "base_url": "http://courses.example/catalog",
            }
        )


@pytest.mark.parametrize("output_format", ["json", "table"])
def test_cli_lists_declarative_providers(output_format: str) -> None:
    result = runner.invoke(cli.app, ["providers", "--format", output_format])

    assert result.exit_code == 0
    for field in ("ms_learn", "openlearn", "aprende", "netacad", "recommended_limit"):
        assert field in result.stdout
    if output_format == "json":
        records = json.loads(result.stdout)
        assert records[1]["strategies"] == ["openlearn_sitemap", "openlearn_catalogue"]


def test_cli_all_provider_flag_skips_waf_sensitive_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_scrape_all(
        limit: int,
        enable_modules: bool,
        skip_waf_sensitive: bool,
    ) -> list[Course]:
        captured.update(
            limit=limit,
            enable_modules=enable_modules,
            skip_waf_sensitive=skip_waf_sensitive,
        )
        return []

    monkeypatch.setattr(cli, "_scrape_all_providers", fake_scrape_all)
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--provider",
            "all",
            "--skip-waf-sensitive",
            "--output",
            "-",
        ],
    )

    assert result.exit_code == 2
    assert captured["skip_waf_sensitive"] is True


def test_cli_keeps_exit_two_for_clean_empty_manifest_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def empty_result(
        self: StrategyRunner,
        provider_id: str,
        adapter: object,
        url: str,
        *,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> list[Course]:
        return []

    monkeypatch.setattr(StrategyRunner, "run", empty_result)
    result = runner.invoke(
        cli.app,
        ["run", "--provider", "aprende", "--output", "-"],
    )

    assert result.exit_code == 2
    assert '"exit_code": 2' in result.stderr


def test_all_provider_runner_omits_waf_sensitive_manifest_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[str] = []

    def fake_run(
        self: StrategyRunner,
        provider_id: str,
        adapter: object,
        url: str,
        *,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> list[Course]:
        attempted.append(provider_id)
        return []

    monkeypatch.setattr(StrategyRunner, "run", fake_run)

    assert cli._scrape_all_providers(0, False, True) == []
    assert "openlearn" not in attempted
    assert set(attempted) == {"ms_learn", "aprende", "netacad"}


@pytest.mark.parametrize("failure", [UpstreamFormatError("bad format"), QualityGateError("bad batch")])
def test_strategy_runner_uses_next_strategy_after_format_or_quality_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    attempted: list[str] = []

    def fake_run_driver(
        driver: str,
        adapter: object,
        url: str,
        provider: ProviderDefinition,
        params: dict[str, Any],
        limit: int,
        enable_modules: bool,
    ) -> list[Course]:
        attempted.append(driver)
        if driver == "example_first":
            raise failure
        return [_course()]

    monkeypatch.setattr("core.strategy.run_driver", fake_run_driver)
    manifest = {"example": _PROVIDER}

    courses = StrategyRunner(manifest).run("example", object(), _PROVIDER.base_url)

    assert [course.name for course in courses] == ["Example course"]
    assert attempted == ["example_first", "example_second"]


def test_strategy_runner_does_not_repeat_waf_blocked_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[str] = []

    def fake_run_driver(
        driver: str,
        adapter: object,
        url: str,
        provider: ProviderDefinition,
        params: dict[str, Any],
        limit: int,
        enable_modules: bool,
    ) -> list[Course]:
        attempted.append(driver)
        raise HTTPStatusError(403, "https://courses.example/catalog", waf_blocked=True)

    monkeypatch.setattr("core.strategy.run_driver", fake_run_driver)
    with pytest.raises(HTTPStatusError, match="403"):
        StrategyRunner({"example": _PROVIDER}).run(
            "example",
            object(),
            _PROVIDER.base_url,
        )

    assert attempted == ["example_first"]


def test_strategy_runner_can_fallback_to_a_different_host_after_waf_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[str] = []
    provider = ProviderDefinition(
        **{
            **_PROVIDER.model_dump(),
            "strategies": [
                {"driver": "blocked_host", "params": {"host": "blocked.example"}},
                {"driver": "fallback_host", "params": {"host": "fallback.example"}},
            ],
        }
    )

    def fake_run_driver(
        driver: str,
        adapter: object,
        url: str,
        provider: ProviderDefinition,
        params: dict[str, Any],
        limit: int,
        enable_modules: bool,
    ) -> list[Course]:
        attempted.append(driver)
        if driver == "blocked_host":
            raise HTTPStatusError(
                403,
                "https://blocked.example/catalog",
                waf_blocked=True,
            )
        return [_course()]

    monkeypatch.setattr("core.strategy.run_driver", fake_run_driver)

    courses = StrategyRunner({"example": provider}).run(
        "example",
        object(),
        provider.base_url,
    )

    assert [course.name for course in courses] == ["Example course"]
    assert attempted == ["blocked_host", "fallback_host"]


def test_strategy_runner_keeps_valid_batch_if_enrichment_strategy_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = [
        _course(
            f"Course {index}",
            url=f"https://courses.example/course/{index}",
            description=None,
        )
        for index in range(5)
    ]

    def fake_run_driver(
        driver: str,
        adapter: object,
        url: str,
        provider: ProviderDefinition,
        params: dict[str, Any],
        limit: int,
        enable_modules: bool,
    ) -> list[Course]:
        if driver == "example_first":
            return original
        raise NetworkError("optional enrichment unavailable")

    monkeypatch.setattr("core.strategy.run_driver", fake_run_driver)

    courses = StrategyRunner({"example": _PROVIDER}).run(
        "example",
        object(),
        _PROVIDER.base_url,
    )

    assert len(courses) == 5
    assert all(course.description is None for course in courses)


def test_generic_sitemap_driver_extracts_jsonld_course_from_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    sitemap_url = "https://courses.example/catalog.xml"
    course_url = "https://courses.example/courses/python"
    sitemap = (
        "<urlset><url><loc>"
        + course_url
        + "</loc></url></urlset>"
    )
    page_html = f"""
    <script type="application/ld+json">
    {json.dumps({"@graph": [{
        "@type": "Course",
        "name": "Python Basics",
        "url": course_url,
        "description": "A complete course about Python fundamentals and practice.",
        "inLanguage": "en",
        "isAccessibleForFree": True,
    }]})}
    </script>
    """
    with respx.mock:
        respx.get(sitemap_url).mock(
            return_value=httpx.Response(200, text=sitemap)
        )
        respx.get(course_url).mock(
            return_value=httpx.Response(200, text=page_html)
        )
        with Crawler() as crawler:
            courses = SitemapJsonLdDriver(
                crawler,
                _PROVIDER,
                {"sitemap_url": sitemap_url, "url_pattern": r"/courses/"},
                limit=1,
            ).scrape()

    assert len(courses) == 1
    assert courses[0].name == "Python Basics"
    assert courses[0].provider == _PROVIDER.name


def test_generic_sitemap_driver_reads_gzip_sitemap_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    index_url = "https://courses.example/sitemap.xml"
    child_url = "https://courses.example/sitemap-courses.xml.gz"
    course_url = "https://courses.example/courses/indexed"
    index = f"<sitemapindex><sitemap><loc>{child_url}</loc></sitemap></sitemapindex>"
    child = gzip.compress(
        f"<urlset><url><loc>{course_url}</loc></url></urlset>".encode()
    )
    page_html = f"""
    <script type="application/ld+json">
    {json.dumps({
        "@type": "Course",
        "name": "Indexed course",
        "url": course_url,
        "description": "A complete course from a gzip sitemap index.",
        "inLanguage": "en",
    })}
    </script>
    """
    with respx.mock:
        respx.get(index_url).mock(return_value=httpx.Response(200, text=index))
        respx.get(child_url).mock(return_value=httpx.Response(200, content=child))
        respx.get(course_url).mock(return_value=httpx.Response(200, text=page_html))
        with Crawler() as crawler:
            courses = SitemapJsonLdDriver(
                crawler,
                _PROVIDER,
                {"sitemap_url": index_url},
            ).scrape()

    assert [course.name for course in courses] == ["Indexed course"]


@pytest.mark.parametrize("status_code", [401, 403, 404, 410])
def test_response_guard_fails_fast_for_definitive_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(status_code, text="blocked")
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(HTTPStatusError):
                crawler.get(url, expected_format="json")

    assert route.call_count == 1


def test_response_guard_rejects_explicit_html_content_type_for_xml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.xml"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                text="maintenance",
                headers={"content-type": "text/html"},
            )
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(UpstreamFormatError):
                crawler.get_bytes(url, expected_format="xml")


def test_response_guard_rejects_html_for_json_without_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(200, text=" \n<html><body>login</body></html>")
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(UpstreamFormatError, match="received HTML"):
                crawler.get(url, expected_format="json")


def test_response_guard_retries_transient_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    monkeypatch.setattr("core.crawler.time.sleep", lambda _: None)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(503, text="temporarily unavailable"),
                httpx.Response(200, json={"courses": []}),
            ]
        )
        with Crawler() as crawler:
            crawler.delay = 0
            assert crawler.get(url, expected_format="json") == '{"courses":[]}'

    assert route.call_count == 2


def test_response_guard_fails_fast_on_explicit_503_waf_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.json"
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(
                503,
                text="temporary block",
                headers={"cf-mitigated": "challenge"},
            )
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(HTTPStatusError) as error:
                crawler.get(url, expected_format="json")

    assert error.value.waf_blocked is True
    assert route.call_count == 1


def test_response_guard_marks_200_antibot_challenge_without_browser_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://courses.example/catalog.xml"
    with respx.mock:
        route = respx.get(url).mock(
            return_value=httpx.Response(
                200,
                text="<html><title>Just a moment...</title></html>",
            )
        )
        with Crawler() as crawler:
            crawler.delay = 0
            with pytest.raises(WAFChallengeError):
                crawler.get(url, expected_format="xml")

    assert route.call_count == 1


@pytest.mark.parametrize(
    ("title", "url", "description", "expected"),
    [
        (
            "Introducción al lenguaje Python",
            "https://courses.example/course/python",
            None,
            "Programación y Desarrollo de Software",
        ),
        (
            "Programa Impulsa 2026",
            "https://courses.example/programa-impulsa-2026",
            None,
            "Pendiente_Categoria",
        ),
    ],
)
def test_conservative_category_inference_and_language_disambiguation(
    title: str,
    url: str,
    description: str | None,
    expected: str,
) -> None:
    course = Course(
        name=title,
        url=url,
        description=description,
        provider="Example Learning",
        in_language="es",
    )

    assert course.category == expected


def test_category_inference_uses_semantic_url_slug() -> None:
    course = Course(
        name="Operations observability workshop",
        url="https://courses.example/azure-monitor",
        provider="Example Learning",
        in_language="en",
    )

    assert course.category == "Redes, Cloud y Ciberseguridad"


def test_category_inference_uses_description_as_low_weight_last_resort() -> None:
    course = Course(
        name="Programa Impulsa 2026",
        url="https://courses.example/programa-impulsa-2026",
        description="El curso desarrolla competencias para configurar Azure Monitor.",
        provider="Example Learning",
        in_language="es",
    )

    assert course.category == "Redes, Cloud y Ciberseguridad"


def test_batch_quality_gate_keeps_courses_without_descriptions() -> None:
    courses = [
        _course("No description", url="https://courses.example/course/1", description=None),
        _course("Short description", url="https://courses.example/course/2", description="Short."),
    ]

    assert BatchQualityGate.validate(courses, _PROVIDER) == courses


@pytest.mark.parametrize(
    "invalid_course",
    [
        _course("Foreign domain", url="https://other.example/course/1"),
        _course("404 Not Found", url="https://courses.example/course/3"),
    ],
)
def test_batch_quality_gate_prunes_one_invalid_course(
    invalid_course: Course,
) -> None:
    batch = [
        _course("Valid one", url="https://courses.example/course/1"),
        _course("Valid two", url="https://courses.example/course/2"),
        invalid_course,
    ]

    valid = BatchQualityGate.validate(batch, _PROVIDER)

    assert len(valid) == 2
    assert invalid_course not in valid


def test_batch_quality_gate_rejects_when_more_than_half_fail() -> None:
    batch = [
        _course("Valid"),
        _course("404 Not Found"),
        _course("Foreign", url="https://elsewhere.example/course"),
    ]

    with pytest.raises(QualityGateError, match="2/3 rejected"):
        BatchQualityGate.validate(batch, _PROVIDER)


def test_batch_quality_gate_requires_a_valid_language_code() -> None:
    with pytest.raises(QualityGateError, match="missing or invalid language"):
        BatchQualityGate.validate(
            [_course(language=None)],
            _PROVIDER,
        )
