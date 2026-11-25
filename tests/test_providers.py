from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
import respx

from config import config
from core.crawler import Crawler
from core.exceptions import NetworkError, ParsingError
from providers import get_provider_by_name
from providers.aprende import AprendeProvider
from providers.ms_learn import MicrosoftLearnProvider
from providers.netacad import NetacadProvider
from providers.openlearn import OpenLearnProvider
from schemas.models import AccessType

_APRENDE_CATALOG_URL = (
    "https://besvc.capacitateparaelempleo.org/api/Courses?platformId=2"
)


def _course_item(
    title: str,
    url: str,
    *,
    duration: int = 90,
    level: str = "beginner",
    locale: str = "es-es",
    products: list[str] | None = None,
    roles: list[str] | None = None,
    subjects: list[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "url": url,
        "summary": "A complete course description with practical learning objectives.",
        "duration_in_minutes": duration,
        "levels": [level],
        "products": products if products is not None else ["azure"],
        "roles": roles if roles is not None else ["cloud-admin"],
        "subjects": subjects if subjects is not None else ["cloud-computing"],
        "locale": locale,
        "icon_url": "/images/course.svg",
    }


def _sitemap_urlset(urls: list[str]) -> str:
    locations = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locations}</urlset>'


def _openlearn_course_html(
    title: str = "OpenLearn Course",
    *,
    credential: str = "Free statement of participation on completion",
) -> str:
    return f"""<!doctype html>
    <html lang="en">
      <head>
        <meta property="og:title" content="{title}">
        <meta property="og:description" content="A free course description with useful learning outcomes and details.">
        <meta property="og:image" content="/images/openlearn-course.jpg">
      </head>
      <body>
        <nav aria-label="Breadcrumb">
          <a>Subjects</a> &gt; <a>Health, Sports &amp; Psychology</a> &gt;
          <a>Free courses</a> &gt; <span>{title}</span>
        </nav>
        <h1>{title}</h1>
        <div>8 hours study</div>
        <h4>Level 1: Introductory</h4>
        <div class="free-statement-block">{credential}</div>
      </body>
    </html>"""


def _aprende_item(
    course_id: int,
    *,
    description: str | None = "Descripción completa para probar los objetivos de aprendizaje.",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": course_id,
        "name": f"Curso Aprende {course_id}",
        "imageUrl": "/images/aprende.jpg",
        "difficultyId": 2,
        "sector": {"name": "Agropecuario"},
        "competences": [{"name": "Cultivo"}],
        "catalogs": [],
        "linkCourses": [],
    }
    if description is not None:
        item["description"] = description
    return item


def _netacad_card(
    slug: str,
    title: str,
    *,
    price: str | None,
    duration: str = "6 Hours",
    level: str = "Beginner",
    credential: str = "",
) -> str:
    price_html = f"<span>Price:<span>{price}</span></span>" if price is not None else ""
    return f"""
    <a class="cardContainer card" href="/courses/{slug}?courseLang=en-US"
       aria-label="{title}. A useful description of the course content.">
      <div role="heading" aria-level="3">{title}</div>
      <div class="description--card" title="A useful description of the course content.">
        A useful description of the course content.
      </div>
      <span>Duration:<span>{duration}</span></span>
      {price_html}
      <span>Difficulty level:<span>{level}</span></span>
      <span>{credential}</span>
    </a>"""


class _FakePage:
    def __init__(self, html: str, wait_timeouts: list[int]) -> None:
        self.html = html
        self.wait_timeouts = wait_timeouts

    def wait_for_function(self, expression: str, timeout: int) -> None:
        self.wait_timeouts.append(timeout)

    def content(self) -> str:
        return self.html


def _mock_netacad_page(
    monkeypatch: pytest.MonkeyPatch,
    html: str,
) -> tuple[list[str], list[int]]:
    opened_urls: list[str] = []
    wait_timeouts: list[int] = []

    @contextmanager
    def fake_open_page(
        crawler: Crawler,
        url: str,
        wait_until: str = "domcontentloaded",
    ) -> Iterator[_FakePage]:
        opened_urls.append(url)
        yield _FakePage(html, wait_timeouts)

    monkeypatch.setattr(Crawler, "open_page", fake_open_page)
    return opened_urls, wait_timeouts


def test_provider_aliases_resolve_all_four_active_providers() -> None:
    assert isinstance(get_provider_by_name("ms_learn"), MicrosoftLearnProvider)
    assert isinstance(get_provider_by_name("mslearn"), MicrosoftLearnProvider)
    assert isinstance(get_provider_by_name("OpenLearn"), OpenLearnProvider)
    assert isinstance(get_provider_by_name("open_learn"), OpenLearnProvider)
    assert isinstance(get_provider_by_name("aprende"), AprendeProvider)
    assert isinstance(get_provider_by_name("netacad"), NetacadProvider)
    assert get_provider_by_name("hubspot") is None


def test_ms_learn_defaults_to_learning_paths_and_maps_course_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    payload = {
        "learningPaths": [
            _course_item(
                "Azure Cloud Administration",
                "https://learn.microsoft.com/es-es/training/paths/azure-admin",
            )
        ],
        "modules": [
            _course_item(
                "Ignored Module",
                "https://learn.microsoft.com/es-es/training/modules/ignored-module",
            )
        ],
    }

    with respx.mock:
        route = respx.get("https://learn.microsoft.com/api/catalog/").mock(
            return_value=httpx.Response(200, json=payload)
        )
        provider = MicrosoftLearnProvider()
        courses = list(provider.scrape(provider.default_url or ""))

    assert len(courses) == 1
    course = courses[0]
    assert course.name == "Azure Cloud Administration"
    assert course.provider == "Microsoft Learn"
    assert course.time_required == "PT1H30M"
    assert course.educational_level == "Principiante"
    assert course.in_language == "es"
    assert course.access_type is AccessType.free_with_certificate
    assert course.keywords == ["cloud computing", "azure", "cloud admin"]
    assert course.category == "Redes, Cloud y Ciberseguridad"
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.params["locale"] == "es-es"
    assert request.url.params["type"] == "learningPaths"


def test_ms_learn_prioritizes_cloud_products_over_generic_roles() -> None:
    item = _course_item(
        "Migración de datos y cargas de trabajo de aplicación a Azure",
        "https://learn.microsoft.com/es-es/training/paths/azure-migration",
        products=["azure", "azure-sql-database"],
        roles=["data-engineer", "solution-architect"],
        subjects=[],
    )

    course = MicrosoftLearnProvider._map_to_course(item, "es-es")

    assert course is not None
    assert course.category == "Redes, Cloud y Ciberseguridad"


def test_ms_learn_can_include_modules_and_uses_duration_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    payload = {
        "learningPaths": [
            _course_item(
                "Learning Path",
                "https://learn.microsoft.com/es-es/training/paths/path",
            )
        ],
        "modules": [
            {
                **_course_item(
                    "Module",
                    "https://learn.microsoft.com/es-es/training/modules/module",
                    duration=0,
                ),
                "duration_in_minutes": None,
                "durationInMinutes": 45,
            }
        ],
    }

    with respx.mock:
        route = respx.get("https://learn.microsoft.com/api/catalog/").mock(
            return_value=httpx.Response(200, json=payload)
        )
        provider = MicrosoftLearnProvider()
        courses = list(
            provider.scrape(
                provider.default_url or "",
                enable_modules=True,
            )
        )

    assert [course.name for course in courses] == ["Learning Path", "Module"]
    assert courses[1].time_required == "PT45M"
    assert route.calls[0].request.url.params["type"] == "learningPaths,modules"


def test_ms_learn_limit_counts_only_valid_courses_and_stops_yielding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    payload = {
        "learningPaths": [
            _course_item("", "https://learn.microsoft.com/es-es/training/paths/invalid"),
            _course_item("First Path", "https://learn.microsoft.com/es-es/training/paths/first"),
            _course_item("Second Path", "https://learn.microsoft.com/es-es/training/paths/second"),
            _course_item("Third Path", "https://learn.microsoft.com/es-es/training/paths/third"),
        ]
    }
    provider = MicrosoftLearnProvider()

    with respx.mock:
        route = respx.get("https://learn.microsoft.com/api/catalog/").mock(
            return_value=httpx.Response(200, json=payload)
        )
        courses = list(provider.scrape(provider.default_url or "", limit=2))

    assert [course.name for course in courses] == ["First Path", "Second Path"]
    assert route.call_count == 1


def test_ms_learn_preserves_explicit_locale_and_type_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    provider = MicrosoftLearnProvider()
    request_url = "https://learn.microsoft.com/api/catalog/?locale=en-us&type=learningPaths"
    payload = {
        "learningPaths": [
            _course_item(
                "English Path",
                "https://learn.microsoft.com/en-us/training/paths/english",
                locale="en-us",
            )
        ],
        "modules": [
            _course_item(
                "Module",
                "https://learn.microsoft.com/en-us/training/modules/module",
                locale="en-us",
            )
        ],
    }

    with respx.mock:
        route = respx.get("https://learn.microsoft.com/api/catalog/").mock(
            return_value=httpx.Response(200, json=payload)
        )
        courses = list(provider.scrape(request_url, enable_modules=True))

    assert len(courses) == 2
    assert courses[0].in_language == "en"
    assert route.calls[0].request.url.params["locale"] == "en-us"
    assert route.calls[0].request.url.params["type"] == "learningPaths"


def test_ms_learn_propagates_http_errors_as_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    with respx.mock:
        respx.get("https://learn.microsoft.com/api/catalog/").mock(
            return_value=httpx.Response(503, text="Unavailable")
        )
        provider = MicrosoftLearnProvider()
        with pytest.raises(NetworkError, match="503"):
            list(provider.scrape(provider.default_url or ""))


def test_openlearn_decompresses_gzip_and_maps_real_course_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    course_url = (
        "https://www.open.edu/openlearn/health-sports-psychology/openlearn-course"
    )
    sitemap = gzip.compress(_sitemap_urlset([course_url]).encode("utf-8"))

    with respx.mock:
        sitemap_route = respx.get(OpenLearnProvider.course_sitemap_url).mock(
            return_value=httpx.Response(200, content=sitemap)
        )
        course_route = respx.get(course_url).mock(
            return_value=httpx.Response(200, text=_openlearn_course_html())
        )
        provider = OpenLearnProvider()
        courses = list(provider.scrape(provider.default_url, limit=1))

    assert len(courses) == 1
    course = courses[0]
    assert course.name == "OpenLearn Course"
    assert course.provider == "OpenLearn (The Open University)"
    assert course.description == "A free course description with useful learning outcomes and details."
    assert course.time_required == "PT8H"
    assert course.educational_level == "Principiante"
    assert course.in_language == "en"
    assert course.category == "Salud y Bienestar"
    assert course.access_type is AccessType.free_with_certificate
    assert "fallback DOM" not in " ".join(course.review_notes)
    assert sitemap_route.call_count == 1
    assert course_route.call_count == 1


def test_openlearn_resolves_course_sitemap_from_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    child_sitemap = (
        "https://www.open.edu/openlearn/pluginfile.php/1/local_ocwsitemap/"
        "sitemap/0/courses_sitemap.xml.gz"
    )
    course_url = "https://www.open.edu/openlearn/health-sports-psychology/index-course"
    index = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<sitemap><loc>{child_sitemap}</loc></sitemap></sitemapindex>"
    )

    with respx.mock:
        child_route = respx.get(OpenLearnProvider.course_sitemap_url).mock(
            side_effect=[
                httpx.Response(503, text="Unavailable"),
                httpx.Response(
                    200,
                    content=gzip.compress(_sitemap_urlset([course_url]).encode("utf-8")),
                ),
            ]
        )
        index_route = respx.get(OpenLearnProvider.sitemap_index_url).mock(
            return_value=httpx.Response(200, text=index)
        )
        course_route = respx.get(course_url).mock(
            return_value=httpx.Response(200, text=_openlearn_course_html("Indexed Course"))
        )
        courses = list(OpenLearnProvider().scrape(OpenLearnProvider.default_url, limit=1))

    assert [course.name for course in courses] == ["Indexed Course"]
    assert child_route.call_count == 2
    assert index_route.call_count == 1
    assert course_route.call_count == 1


def test_openlearn_falls_back_to_paginated_catalog_and_stops_at_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    catalog_url = OpenLearnProvider.default_url
    first_url = "https://www.open.edu/openlearn/health-sports-psychology/first-course"
    second_url = "https://www.open.edu/openlearn/science-maths-technology/second-course"
    catalog_page = (
        '<a href="/openlearn/health-sports-psychology/first-course/content-section-0?active-tab=description-tab">First</a>'
        '<a href="/openlearn/science-maths-technology/second-course/content-section-overview">Second</a>'
    )
    page_zero = OpenLearnProvider._catalog_page_url(catalog_url, 0)
    page_one = OpenLearnProvider._catalog_page_url(catalog_url, 1)

    with respx.mock:
        respx.get(OpenLearnProvider.course_sitemap_url).mock(
            return_value=httpx.Response(503, text="Unavailable")
        )
        respx.get(OpenLearnProvider.sitemap_index_url).mock(
            return_value=httpx.Response(503, text="Unavailable")
        )
        catalog_route = respx.get(page_zero).mock(
            return_value=httpx.Response(200, text=catalog_page)
        )
        unused_page_route = respx.get(page_one).mock(
            return_value=httpx.Response(200, text="")
        )
        first_route = respx.get(first_url).mock(
            return_value=httpx.Response(200, text=_openlearn_course_html("First Course"))
        )
        second_route = respx.get(second_url).mock(
            return_value=httpx.Response(200, text=_openlearn_course_html("Second Course"))
        )
        courses = list(OpenLearnProvider().scrape(catalog_url, limit=1))

    assert [course.name for course in courses] == ["First Course"]
    assert catalog_route.call_count == 1
    assert unused_page_route.call_count == 0
    assert first_route.call_count == 1
    assert second_route.call_count == 0


def test_openlearn_individual_course_does_not_fetch_sitemaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://www.open.edu/openlearn/health-sports-psychology/single-course"

    with respx.mock:
        course_route = respx.get(url).mock(
            return_value=httpx.Response(
                200,
                text=_openlearn_course_html(
                    "Single Course",
                    credential="No credential information on this page.",
                ),
            )
        )
        sitemap_route = respx.get(OpenLearnProvider.course_sitemap_url).mock(
            return_value=httpx.Response(500)
        )
        courses = list(OpenLearnProvider().scrape(url))

    assert [course.name for course in courses] == ["Single Course"]
    assert courses[0].access_type is AccessType.free_no_certificate
    assert course_route.call_count == 1
    assert sitemap_route.call_count == 0


def test_aprende_maps_catalog_course_and_uses_repository_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    payload = {"courses": [_aprende_item(101)], "links": []}

    with respx.mock:
        route = respx.get(_APRENDE_CATALOG_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        courses = list(AprendeProvider().scrape(AprendeProvider.default_url))

    assert len(courses) == 1
    course = courses[0]
    assert course.name == "Curso Aprende 101"
    assert course.provider == "Aprende.org (Fundación Carlos Slim)"
    assert course.in_language == "es"
    assert course.access_type is AccessType.free_with_certificate
    assert course.educational_level == "Intermedio"
    assert course.description == "Descripción completa para probar los objetivos de aprendizaje."
    assert course.keywords == ["Cultivo"]
    assert route.calls[0].request.headers["user-agent"] == config.USER_AGENT


def test_aprende_detail_is_lazy_and_missing_description_stays_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    detail_one = "https://besvc.capacitateparaelempleo.org/api/Courses/201?platformId=2"
    detail_two = "https://besvc.capacitateparaelempleo.org/api/Courses/202?platformId=2"
    payload = {"courses": [_aprende_item(201, description=None), _aprende_item(202, description=None)]}

    with respx.mock:
        respx.get(_APRENDE_CATALOG_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        detail_one_route = respx.get(detail_one).mock(
            return_value=httpx.Response(200, json={"id": 201, "name": "Curso Aprende 201"})
        )
        detail_two_route = respx.get(detail_two).mock(
            return_value=httpx.Response(200, json={"id": 202, "name": "Curso Aprende 202"})
        )
        courses = list(AprendeProvider().scrape(AprendeProvider.default_url, limit=1))

    assert len(courses) == 1
    assert courses[0].description is None
    assert courses[0].needs_review is True
    assert detail_one_route.call_count == 1
    assert detail_two_route.call_count == 0


@pytest.mark.parametrize("status_code", [401, 403, 503])
def test_aprende_http_errors_propagate_as_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    with respx.mock:
        respx.get(_APRENDE_CATALOG_URL).mock(
            return_value=httpx.Response(status_code, text="Unavailable")
        )
        with pytest.raises(NetworkError, match=str(status_code)):
            list(AprendeProvider().scrape(AprendeProvider.default_url))


def test_aprende_invalid_json_raises_parsing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    with respx.mock:
        respx.get(_APRENDE_CATALOG_URL).mock(
            return_value=httpx.Response(200, text="{invalid")
        )
        with pytest.raises(ParsingError, match="invalid JSON"):
            list(AprendeProvider().scrape(AprendeProvider.default_url))


def test_netacad_uses_rendered_catalog_filters_paid_items_and_honors_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    html = f"""<!doctype html>
    <html lang="en"><body>
      <h2>Cybersecurity</h2>
      {_netacad_card("free-one", "Free One", price="Free", credential="Free digital badge")}
      {_netacad_card("paid", "Paid Course", price="$49")}
      {_netacad_card("unknown-price", "Unknown Price", price=None)}
      {_netacad_card("free-two", "Free Two", price="Gratis", duration="30 Minutes", level="Intermediate")}
    </body></html>"""
    opened_urls, wait_timeouts = _mock_netacad_page(monkeypatch, html)

    courses = list(
        NetacadProvider().scrape(
            NetacadProvider.default_url,
            render=False,
            limit=2,
        )
    )

    assert [course.name for course in courses] == ["Free One", "Free Two"]
    assert courses[0].time_required == "PT6H"
    assert courses[0].educational_level == "Principiante"
    assert courses[0].in_language == "en"
    assert courses[0].category == "Redes, Cloud y Ciberseguridad"
    assert courses[0].access_type is AccessType.free_with_certificate
    assert courses[1].time_required == "PT30M"
    assert courses[1].educational_level == "Intermedio"
    assert courses[1].access_type is AccessType.free_no_certificate
    assert opened_urls == [NetacadProvider.default_url]
    assert wait_timeouts == [15_000]


def test_netacad_individual_detail_uses_extruct_and_requires_free_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    url = "https://www.netacad.com/courses/python-essentials-1?courseLang=en-US"
    structured = {
        "@context": "https://schema.org",
        "@type": "Course",
        "name": "Python Essentials 1",
        "url": url,
        "description": "A complete Python course description with learning outcomes.",
        "inLanguage": "en",
    }
    html = (
        f'<script type="application/ld+json">{json.dumps(structured)}</script>'
        "<h1>Python Essentials 1</h1><p>Price: Free</p>"
    )
    opened_urls, _ = _mock_netacad_page(monkeypatch, html)

    courses = list(NetacadProvider().scrape(url, limit=1))

    assert [course.name for course in courses] == ["Python Essentials 1"]
    assert courses[0].access_type is AccessType.free_no_certificate
    assert courses[0].in_language == "en"
    assert opened_urls == [url]
