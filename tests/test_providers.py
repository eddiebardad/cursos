from __future__ import annotations

import json

import httpx
import pytest
import respx

from config import config
from core.exceptions import NetworkError
from providers import get_provider_by_name
from providers.hubspot import HubspotProvider
from providers.ms_learn import MicrosoftLearnProvider
from schemas.models import AccessType


def _course_item(
    title: str,
    url: str,
    *,
    duration: int = 90,
    level: str = "beginner",
    locale: str = "es-es",
) -> dict[str, object]:
    return {
        "title": title,
        "url": url,
        "summary": "A complete course description with practical learning objectives.",
        "duration_in_minutes": duration,
        "levels": [level],
        "products": ["azure"],
        "roles": ["cloud-admin"],
        "subjects": ["cloud-computing"],
        "locale": locale,
        "icon_url": "/images/course.svg",
    }


def _hubspot_course_html(title: str, url: str) -> str:
    structured = {
        "@context": "https://schema.org",
        "@type": "Course",
        "name": title,
        "url": url,
        "description": "A practical course description with clear learning outcomes.",
        "inLanguage": "es",
    }
    return f'<script type="application/ld+json">{json.dumps(structured)}</script>'


def _sitemap_urlset(urls: list[str]) -> str:
    locations = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locations}</urlset>'


def test_provider_aliases_resolve_microsoft_learn_and_hubspot() -> None:
    assert isinstance(get_provider_by_name("ms_learn"), MicrosoftLearnProvider)
    assert isinstance(get_provider_by_name("mslearn"), MicrosoftLearnProvider)
    assert isinstance(get_provider_by_name("MicrosoftLearn"), MicrosoftLearnProvider)
    assert isinstance(get_provider_by_name("hubspot"), HubspotProvider)


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
    assert course.keywords == ["cloud computing", "cloud admin", "azure"]
    assert course.category == "Redes, Cloud y Ciberseguridad"
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.params["locale"] == "es-es"
    assert request.url.params["type"] == "learningPaths"


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


def test_hubspot_urlset_filters_to_requested_spanish_course_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    course_url = "https://academy.hubspot.com/es/courses/inbound-marketing"
    urls = [
        "https://academy.hubspot.com/es/courses",
        course_url,
        "https://academy.hubspot.com/es/courses/tag/marketing",
        "https://academy.hubspot.com/en/courses/inbound-marketing",
    ]

    with respx.mock:
        sitemap_route = respx.get(HubspotProvider.sitemap_url).mock(
            return_value=httpx.Response(200, text=_sitemap_urlset(urls))
        )
        course_route = respx.get(course_url).mock(
            return_value=httpx.Response(
                200,
                text=_hubspot_course_html("Inbound Marketing", course_url),
            )
        )
        provider = HubspotProvider()
        courses = list(provider.scrape(provider.default_url or ""))

    assert len(courses) == 1
    assert courses[0].name == "Inbound Marketing"
    assert courses[0].provider == "HubSpot Academy"
    assert courses[0].access_type is AccessType.free_with_certificate
    assert sitemap_route.call_count == 1
    assert course_route.call_count == 1


def test_hubspot_sitemap_index_is_lazy_and_limit_stops_remaining_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    sitemap_part_one = "https://academy.hubspot.com/sitemap-courses-1.xml"
    sitemap_part_two = "https://academy.hubspot.com/sitemap-courses-2.xml"
    first_url = "https://academy.hubspot.com/es/courses/first"
    second_url = "https://academy.hubspot.com/es/courses/second"
    third_url = "https://academy.hubspot.com/es/courses/third"
    index = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<sitemap><loc>{sitemap_part_one}</loc></sitemap>"
        f"<sitemap><loc>{sitemap_part_two}</loc></sitemap>"
        "</sitemapindex>"
    )

    with respx.mock:
        index_route = respx.get(HubspotProvider.sitemap_url).mock(
            return_value=httpx.Response(200, text=index)
        )
        part_one_route = respx.get(sitemap_part_one).mock(
            return_value=httpx.Response(200, text=_sitemap_urlset([first_url, second_url]))
        )
        part_two_route = respx.get(sitemap_part_two).mock(
            return_value=httpx.Response(200, text=_sitemap_urlset([third_url]))
        )
        first_route = respx.get(first_url).mock(
            return_value=httpx.Response(200, text=_hubspot_course_html("First", first_url))
        )
        second_route = respx.get(second_url).mock(
            return_value=httpx.Response(200, text=_hubspot_course_html("Second", second_url))
        )
        third_route = respx.get(third_url).mock(
            return_value=httpx.Response(200, text=_hubspot_course_html("Third", third_url))
        )

        provider = HubspotProvider()
        courses = list(provider.scrape(provider.default_url or "", limit=1))

    assert [course.name for course in courses] == ["First"]
    assert index_route.call_count == 1
    assert part_one_route.call_count == 1
    assert part_two_route.call_count == 0
    assert first_route.call_count == 1
    assert second_route.call_count == 0
    assert third_route.call_count == 0


def test_hubspot_individual_course_url_uses_extruct_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    course_url = "https://academy.hubspot.com/fr/courses/marketing"

    with respx.mock:
        course_route = respx.get(course_url).mock(
            return_value=httpx.Response(
                200,
                text=_hubspot_course_html("Marketing", course_url),
            )
        )
        sitemap_route = respx.get(HubspotProvider.sitemap_url).mock(
            return_value=httpx.Response(500)
        )
        provider = HubspotProvider()
        courses = list(provider.scrape(course_url))

    assert len(courses) == 1
    assert courses[0].provider == "HubSpot Academy"
    assert courses[0].access_type is AccessType.free_with_certificate
    assert course_route.call_count == 1
    assert sitemap_route.call_count == 0


def test_hubspot_falls_back_to_catalog_links_when_sitemap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "COURTESY_DELAY", 0.0)
    catalog_url = "https://academy.hubspot.com/es/courses"
    course_url = "https://academy.hubspot.com/es/courses/course-from-catalog"
    catalog_html = '<a href="/es/courses/course-from-catalog">Course</a>'

    with respx.mock:
        sitemap_route = respx.get(HubspotProvider.sitemap_url).mock(
            return_value=httpx.Response(503)
        )
        catalog_route = respx.get(catalog_url).mock(
            return_value=httpx.Response(200, text=catalog_html)
        )
        course_route = respx.get(course_url).mock(
            return_value=httpx.Response(
                200,
                text=_hubspot_course_html("Catalog Course", course_url),
            )
        )
        provider = HubspotProvider()
        courses = list(provider.scrape(catalog_url, limit=1))

    assert [course.name for course in courses] == ["Catalog Course"]
    assert sitemap_route.call_count == 1
    assert catalog_route.call_count == 1
    assert course_route.call_count == 1
