from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest
import respx
from playwright.sync_api import Error as PlaywrightError

from core.crawler import Crawler, crawl_site
from core.exceptions import ScraperException
from core.extractor import extract_course_candidates
from core.parser import Parser, parse_course_page


def test_jsonld_graph_candidate_flattens_course_instance_fields() -> None:
    html = """
    <script type="application/ld+json">
    {
      "@graph": [
        {
          "@type": ["Course", "LearningResource"],
          "name": "Python for Data",
          "description": "A complete course covering Python and practical data skills.",
          "url": "/courses/python-data",
          "provider": {"@type": "Organization", "name": "Open Academy"},
          "hasCourseInstance": {
            "@type": "CourseInstance",
            "instructor": {"@type": "Person", "name": "Ada Lovelace"},
            "inLanguage": "es-ES",
            "timeRequired": "PT2H"
          },
          "keywords": "Python, SQL; Datos",
          "about": {"@type": "Thing", "name": "Programación"},
          "coursePrerequisites": [{"name": "Basic computer skills"}],
          "image": {"@type": "ImageObject", "contentUrl": "/images/python.jpg"}
        }
      ]
    }
    </script>
    """

    candidates = extract_course_candidates(html, "https://academy.example/courses/catalog")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["name"] == "Python for Data"
    assert candidate["url"] == "https://academy.example/courses/python-data"
    assert candidate["provider"] == "Open Academy"
    assert candidate["authors"] == ["Ada Lovelace"]
    assert candidate["in_language"] == "es"
    assert candidate["time_required"] == "PT2H"
    assert candidate["keywords"] == ["Python", "SQL", "Datos"]
    assert candidate["course_prerequisites"] == ["Basic computer skills"]
    assert candidate["image"] == "/images/python.jpg"

    course = parse_course_page(html, "https://academy.example/courses/catalog")
    assert course is not None
    assert course.provider == "Open Academy"
    assert course.authors == ["Ada Lovelace"]
    assert course.time_required == "PT2H"


def test_jsonld_traverses_main_entity_and_item_list_elements() -> None:
    html = """
    <script type="application/ld+json">
    {
      "@type": "WebPage",
      "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
          {"@type": "Course", "name": "Course One", "url": "/one"},
          {"item": {"@type": "Course", "name": "Course Two", "url": "/two"}}
        ]
      }
    }
    </script>
    """

    candidates = extract_course_candidates(html, "https://academy.example/catalog")
    assert [candidate["name"] for candidate in candidates] == ["Course One", "Course Two"]


@pytest.mark.parametrize(
    "course_type",
    [
        "Course",
        "schema:Course",
        "https://schema.org/Course",
        "http://schema.org/Course",
    ],
)
def test_supported_schema_course_type_forms(course_type: str) -> None:
    html = f"""
    <script type="application/ld+json">
    {{"@type":"{course_type}","name":"Typed Course","url":"/typed"}}
    </script>
    """

    candidates = extract_course_candidates(html, "https://academy.example/catalog")
    assert len(candidates) == 1
    assert candidates[0]["name"] == "Typed Course"


def test_microdata_is_extracted_and_jsonld_has_priority() -> None:
    microdata = """
    <div itemscope itemtype="https://schema.org/Course">
      <span itemprop="name">Microdata Course</span>
      <meta itemprop="description" content="A detailed microdata course description for learners.">
      <link itemprop="url" href="/microdata-course">
    </div>
    """
    candidates = extract_course_candidates(microdata, "https://academy.example/catalog")
    assert len(candidates) == 1
    assert candidates[0]["name"] == "Microdata Course"
    assert candidates[0]["url"] == "https://academy.example/microdata-course"

    combined = """
    <script type="application/ld+json">
    {"@type":"Course","name":"JSON-LD Course","url":"/jsonld","description":"A complete JSON-LD course description."}
    </script>
    """ + microdata
    prioritized = extract_course_candidates(combined, "https://academy.example/catalog")
    assert [candidate["name"] for candidate in prioritized] == [
        "JSON-LD Course",
        "Microdata Course",
    ]
    course = parse_course_page(combined, "https://academy.example/catalog")
    assert course is not None
    assert course.name == "JSON-LD Course"


def test_opengraph_enriches_course_but_does_not_identify_one() -> None:
    course_html = """
    <meta property="og:title" content="OpenGraph Course">
    <meta property="og:description" content="A useful course description provided by OpenGraph metadata.">
    <meta property="og:image" content="/images/course.png">
    <meta property="og:locale" content="es_MX">
    <script type="application/ld+json">
    {"@type":"Course","url":"/course"}
    </script>
    """
    candidates = extract_course_candidates(course_html, "https://academy.example/catalog")
    assert candidates[0]["name"] == "OpenGraph Course"
    assert candidates[0]["description"].startswith("A useful course")
    assert candidates[0]["image"] == "/images/course.png"
    assert candidates[0]["in_language"] == "es"

    og_only = """
    <meta property="og:type" content="website">
    <meta property="og:title" content="Not a course">
    <meta property="og:description" content="Generic metadata without a Course descriptor.">
    """
    assert extract_course_candidates(og_only, "https://academy.example/page") == []


@pytest.mark.parametrize(
    "structured_course",
    [
        '"isAccessibleForFree": false',
        '"offers": {"@type":"Offer","price":"49.99"}',
    ],
)
def test_parse_rejects_paid_structured_courses(structured_course: str) -> None:
    html = f"""
    <script type="application/ld+json">
    {{
      "@type": "Course",
      "name": "Paid Course",
      "description": "A course description long enough to pass the quality checks.",
      "url": "/paid-course",
      "inLanguage": "en",
      {structured_course}
    }}
    </script>
    """

    assert parse_course_page(html, "https://academy.example/catalog") is None


def test_dom_fallback_requires_real_course_content_and_honors_guardrails() -> None:
    html = """
    <html lang="es">
      <head>
        <meta name="description" content="Descripción extensa y útil para una ficha educativa.">
        <meta property="og:image" content="/images/fallback.jpg">
      </head>
      <body>
        <main>
          <h1>Curso de programación</h1>
          <p>Aprende programación con ejercicios y explicaciones prácticas para principiantes.</p>
        </main>
      </body>
    </html>
    """
    course = parse_course_page(html, "https://academy.example/courses/programming")
    assert course is not None
    assert course.needs_review is True
    assert course.review_notes == [
        "Extraído mediante fallback DOM sin metadatos estructurados Course"
    ]
    assert course.image == "https://academy.example/images/fallback.jpg"

    assert parse_course_page(
        html,
        "https://academy.example/courses/programming",
        allow_dom_fallback=False,
    ) is None
    assert parse_course_page(html, "https://academy.example/login") is None
    assert parse_course_page(html, "https://academy.example/privacy") is None
    assert parse_course_page(html, "https://academy.example/") is None
    assert parse_course_page("<p>Sin encabezado ni descripción</p>", "https://academy.example/course") is None


def test_defaults_only_fill_values_missing_from_structured_course() -> None:
    html = """
    <script type="application/ld+json">
    {"@type":"Course","name":"Specific Provider Course","provider":{"name":"Page Provider"},"url":"/course"}
    </script>
    """

    course = parse_course_page(
        html,
        "https://academy.example/catalog",
        defaults={"provider": "Default Provider", "in_language": "es"},
    )
    assert course is not None
    assert course.provider == "Page Provider"
    assert course.in_language == "es"


def test_free_certificate_credential_is_mapped_when_explicit() -> None:
    html = """
    <script type="application/ld+json">
    {"@type":"Course","name":"Certified Course","url":"/certified",
     "educationalCredentialAwarded":"Free certificate"}
    </script>
    """

    candidates = extract_course_candidates(html, "https://academy.example/catalog")
    assert candidates[0]["access_type"].value == "free_with_certificate"


def test_internal_links_filter_schemes_fragments_and_duplicates() -> None:
    soup = Parser.parse_html(
        """
        <a href="mailto:hello@example.test">Mail</a>
        <a href="tel:+100000000">Phone</a>
        <a href="javascript:void(0)">Script</a>
        <a href="data:text/plain,x">Data</a>
        <a href="/course#overview">Course</a>
        <a href="/course#details">Duplicate</a>
        <a href="https://other.example/course">External</a>
        """
    )

    assert Parser.extract_internal_links(soup, "https://academy.example/catalog") == [
        "https://academy.example/course"
    ]


def test_http_requests_do_not_start_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playwright_factory = Mock()
    monkeypatch.setattr("core.crawler.sync_playwright", playwright_factory)
    with respx.mock:
        route = respx.get("https://academy.example/page").mock(
            return_value=httpx.Response(200, text="<html>static</html>")
        )
        with Crawler() as crawler:
            crawler.delay = 0
            assert crawler.get("https://academy.example/page") == "<html>static</html>"

    assert route.called
    playwright_factory.assert_not_called()


def _mock_page(html: str, goto_error: Exception | None = None) -> Mock:
    page = Mock()
    page.content.return_value = html
    if goto_error is not None:
        page.goto.side_effect = goto_error
    return page


def test_rendered_requests_reuse_chromium_and_close_each_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [_mock_page(f"<html>{index}</html>") for index in range(3)]
    browser_context = Mock()
    browser_context.new_page.side_effect = pages
    browser = Mock()
    browser.new_context.return_value = browser_context
    playwright = Mock()
    playwright.chromium.launch.return_value = browser
    manager = Mock()
    manager.start.return_value = playwright
    playwright_factory = Mock(return_value=manager)
    monkeypatch.setattr("core.crawler.sync_playwright", playwright_factory)

    with Crawler() as crawler:
        crawler.delay = 0
        results = [crawler.get(f"https://academy.example/{i}", render=True) for i in range(3)]

    assert results == ["<html>0</html>", "<html>1</html>", "<html>2</html>"]
    playwright_factory.assert_called_once_with()
    manager.start.assert_called_once_with()
    playwright.chromium.launch.assert_called_once_with(headless=True)
    browser.new_context.assert_called_once_with(
        user_agent="CursodexBot/1.0 (+https://cursodex.com; academic research index)"
    )
    assert browser_context.new_page.call_count == 3
    for page in pages:
        page.goto.assert_called_once()
        assert page.goto.call_args.kwargs["wait_until"] == "domcontentloaded"
        page.close.assert_called_once_with()
    browser_context.close.assert_called_once_with()
    browser.close.assert_called_once_with()
    playwright.stop.assert_called_once_with()


def test_browser_and_playwright_close_after_rendered_request_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _mock_page("", RuntimeError("navigation failed"))
    browser_context = Mock()
    browser_context.new_page.return_value = page
    browser = Mock()
    browser.new_context.return_value = browser_context
    playwright = Mock()
    playwright.chromium.launch.return_value = browser
    manager = Mock()
    manager.start.return_value = playwright
    monkeypatch.setattr("core.crawler.sync_playwright", Mock(return_value=manager))

    with pytest.raises(RuntimeError, match="navigation failed"):
        with Crawler() as crawler:
            crawler.delay = 0
            crawler.get("https://academy.example/fails", render=True)

    page.close.assert_called_once_with()
    browser_context.close.assert_called_once_with()
    browser.close.assert_called_once_with()
    playwright.stop.assert_called_once_with()


def test_missing_chromium_has_actionable_scraper_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = Mock()
    manager.start.side_effect = PlaywrightError("executable doesn't exist")
    monkeypatch.setattr("core.crawler.sync_playwright", Mock(return_value=manager))

    with pytest.raises(ScraperException, match="uv run playwright install chromium"):
        with Crawler() as crawler:
            crawler.delay = 0
            crawler.get("https://academy.example/course", render=True)


def test_bfs_filters_assets_and_stops_at_course_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import config

    monkeypatch.setattr(config, "COURTESY_DELAY", 0)
    start_url = "https://academy.example/catalog"
    first_course_url = "https://academy.example/courses/first"
    second_course_url = "https://academy.example/courses/second"
    static_urls = [
        "https://academy.example/files/manual.PDF?dl=1",
        "https://academy.example/images/banner.PNG",
        "https://academy.example/assets/site.css",
        "https://academy.example/data/catalog.json",
    ]
    start_html = """
    <a href="mailto:hello@example.test">Mail</a>
    <a href="javascript:void(0)">Script</a>
    <a href="/files/manual.PDF?dl=1">PDF</a>
    <a href="/images/banner.PNG">Image</a>
    <a href="/assets/site.css">CSS</a>
    <a href="/data/catalog.json">JSON</a>
    <a href="/courses/first">First</a>
    <a href="/courses/second">Second</a>
    """
    course_html = """
    <script type="application/ld+json">
    {"@type":"Course","name":"First Course","url":"/courses/first",
     "description":"A structured course description with enough detail.",
     "inLanguage":"en"}
    </script>
    """

    with respx.mock:
        start_route = respx.get(start_url).mock(
            return_value=httpx.Response(200, text=start_html)
        )
        course_route = respx.get(first_course_url).mock(
            return_value=httpx.Response(200, text=course_html)
        )
        second_route = respx.get(second_course_url).mock(
            return_value=httpx.Response(200, text=course_html.replace("First Course", "Second Course"))
        )
        static_routes = [
            respx.get(static_url).mock(return_value=httpx.Response(200, text="static"))
            for static_url in static_urls
        ]
        courses = crawl_site(start_url, limit=1)

    assert len(courses) == 1
    assert courses[0].name == "First Course"
    assert start_route.call_count == 1
    assert course_route.call_count == 1
    assert second_route.call_count == 0
    assert all(route.call_count == 0 for route in static_routes)
