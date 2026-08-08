#!/usr/bin/env python3
"""Generic course scraper for websites like aprende.org.

The sample workbook headers discovered from the Excel file include:
- ID
- Title
- Excerpt
- Permalink
- Featured
- Categorías de curso
- Etiquetas de curso
- _lp_duration
- thim_course_skill_level
- thim_course_language
- thim_course_duration
- _lp_free
- _lp_price
- _lp_level
- _lp_external_link_buy_course
- Author Username

This scraper asks for a website, crawls internal pages, detects course pages, extracts
available information for each course, and writes a CSV with the collected fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import html
from collections import deque
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
    from bs4.element import Tag
except ImportError:
    BeautifulSoup = None

# Known workbook headers discovered from the example .xlsx file.
WORKBOOK_HEADERS = [
    "ID",
    "Title",
    "Excerpt",
    "Permalink",
    "Featured",
    "Categorías de curso",
    "Etiquetas de curso",
    "_lp_duration",
    "thim_course_skill_level",
    "thim_course_language",
    "thim_course_duration",
    "_lp_free",
    "_lp_price",
    "_lp_level",
    "_lp_external_link_buy_course",
    "Author Username",
]

OUTPUT_FIELDS = WORKBOOK_HEADERS + ["site", "raw_jsonld"]

FIELD_MAP = {
    "id": "ID",
    "title": "Title",
    "excerpt": "Excerpt",
    "page_url": "Permalink",
    "featured_image": "Featured",
    "imageUrl": "URL Image",
    "categories": "Categorías de curso",
    "tags": "Etiquetas de curso",
    "duration": "_lp_duration",
    "language": "thim_course_language",
    "free": "_lp_free",
    "price": "_lp_price",
    "level": "_lp_level",
    "external_link": "_lp_external_link_buy_course",
    "author": "Author Username",
}

APRRENDE_API_ROOT = "https://besvc.capacitateparaelempleo.org"
APRRENDE_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Course Scraper)",
    "includeHATEOAS": "N",
    "platformId": "2",
    "x-languageCode": "es",
    "x-isApp": "false",
    "X-API-KEY": "",
}



COURSE_KEYWORDS = [
    "curso",
    "course",
    "certificación",
    "certificacion",
    "learning",
    "capacítate",
    "capacitate",
    "formación",
    "formacion",
    "ruta de aprendizaje",
    "capacítate para el empleo",
    "capacitate para el empleo",
]

# Add more generic English and structural keywords to help detect course pages
COURSE_KEYWORDS.extend([
    "lesson",
    "module",
    "syllabus",
    "enroll",
    "register",
    "signup",
    "certificate",
    "certification",
    "training",
    "curriculum",
    "hours",
    "minutes",
])

DURATION_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*(?:horas|hora|hrs|hr|minutes|minutos|mins|min)",
    r"(\d+)\s*(?:h|m)\b",
]

LANGUAGE_LABELS = [
    "español",
    "spanish",
    "inglés",
    "ingles",
    "english",
    "francés",
    "frances",
    "portugués",
    "portugues",
    "alemán",
    "aleman",
    "japonés",
    "japones",
]

PRICE_PATTERNS = [
    r"\$\s*\d+[\d,.]*",
    r"gratis",
    r"free",
    r"valor\s*\$\s*\d+[\d,.]*",
]


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "a":
            href = None
            for name, value in attrs:
                if name.lower() == "href" and value:
                    href = value
                    break
            if href:
                self.links.append(href)


def normalize_url(href: str, base_url: str) -> Optional[str]:
    href = href.strip()
    if not href or href.startswith("mailto:") or href.startswith("javascript:"):
        return None
    parsed = urllib.parse.urljoin(base_url, href)
    parsed = parsed.split("#")[0]
    if parsed.startswith("http://") or parsed.startswith("https://"):
        return parsed
    return None


def same_domain(url: str, base_url: str) -> bool:
    try:
        return urllib.parse.urlparse(url).netloc.lower() == urllib.parse.urlparse(base_url).netloc.lower()
    except Exception:
        return False


def fetch_html(url: str, timeout: int = 20) -> Tuple[str, str]:
    headers = {"User-Agent": "Mozilla/5.0 (Course Scraper)"}
    if requests:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text, response.url
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="ignore")
        return html, response.geturl()


def render_fetch(url: str, timeout: int = 30) -> Tuple[str, str]:
    """Render the URL with Playwright and return (html, final_url).

    Requires: `pip install playwright` and `playwright install`.
    If Playwright is not installed, raises ImportError with instructions.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise ImportError("Playwright is required for rendering. Install with: pip install playwright; then run: playwright install") from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        html = page.content()
        final = page.url
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        return html, final


def parse_links(html: str, base_url: str) -> List[str]:
    links: List[str] = []
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            normalized = normalize_url(a["href"], base_url)
            if normalized:
                links.append(normalized)
    else:
        extractor = LinkExtractor()
        extractor.feed(html)
        for href in extractor.links:
            normalized = normalize_url(href, base_url)
            if normalized:
                links.append(normalized)
    return links


def extract_text_from_tag(tag: Any) -> str:
    if BeautifulSoup and isinstance(tag, Tag):
        return tag.get_text(separator=" ", strip=True)
    return ""  # type: ignore[return-value]


def page_text(html: str) -> str:
    """Return cleaned visible text from an HTML document."""
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for el in soup(["script", "style", "noscript"]):
            try:
                el.decompose()
            except Exception:
                pass
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)
    # crude fallback
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_jsonld(html: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, list):
                    results.extend(data)
                elif isinstance(data, dict):
                    results.append(data)
            except json.JSONDecodeError:
                continue
    else:
        # crude fallback: find JSON-LD blocks via regex
        for match in re.finditer(r"<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", html, flags=re.S | re.I):
            block = match.group(1).strip()
            try:
                data = json.loads(block)
                if isinstance(data, list):
                    results.extend(data)
                elif isinstance(data, dict):
                    results.append(data)
            except json.JSONDecodeError:
                continue
    return results


def parse_meta(html: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title:
            data["title"] = soup.title.get_text(strip=True)
        for tag in soup.find_all("meta"):
            if not tag.attrs:
                continue
            if tag.get("name"):
                key = tag["name"].strip().lower()
                value = tag.get("content", "").strip()
                if value:
                    data[key] = value
            elif tag.get("property"):
                key = tag["property"].strip().lower()
                value = tag.get("content", "").strip()
                if value:
                    data[key] = value
    else:
        title_match = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
        if title_match:
            data["title"] = title_match.group(1).strip()
        for match in re.finditer(r"<meta\s+([^>]+)>", html, flags=re.I):
            attrs = match.group(1)
            name = re.search(r"name=['\"]([^'\"]+)['\"]", attrs, flags=re.I)
            prop = re.search(r"property=['\"]([^'\"]+)['\"]", attrs, flags=re.I)
            content = re.search(r"content=['\"]([^'\"]+)['\"]", attrs, flags=re.I)
            if content:
                key = name.group(1).strip().lower() if name else prop.group(1).strip().lower() if prop else None
                if key:
                    data[key] = content.group(1).strip()
    return data


def find_course_fields(text: str) -> Dict[str, str]:
    lower_text = text.lower()
    record: Dict[str, str] = {}

    for pattern in DURATION_PATTERNS:
        match = re.search(pattern, lower_text)
        if match:
            record["duration"] = match.group(0).strip()
            break

    for label in LANGUAGE_LABELS:
        if label in lower_text:
            record["language"] = label.capitalize()
            break

    found_price = None
    for pattern in PRICE_PATTERNS:
        match = re.search(pattern, lower_text)
        if match:
            found_price = match.group(0).strip()
            break
    if found_price:
        if "gratis" in found_price.lower() or "free" in found_price.lower():
            record["free"] = "yes"
            record["price"] = "0"
        else:
            record["price"] = found_price
            record["free"] = "no"

    if "nivel" in lower_text or "nivel" in text:
        level_match = re.search(r"nivel\s*[:\-]?\s*([A-Za-z0-9 ]{1,40})", text, flags=re.I)
        if level_match:
            record["level"] = level_match.group(1).strip()

    author_match = re.search(r"(?:autor|instructor|profesor|docente|teacher)[:\-]?\s*([^\n\r<]{2,80})", text, flags=re.I)
    if author_match:
        record["author"] = author_match.group(1).strip()

    return record


def strip_html_text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


def is_aprende_site(url: str) -> bool:
    try:
        hostname = urllib.parse.urlparse(url).netloc.lower()
        return hostname.endswith("aprende.org")
    except Exception:
        return False


def extract_aprende_course_record(course: Dict[str, Any], source_url: str) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": course.get("id"),
        "title": course.get("name"),
        "excerpt": strip_html_text(course.get("description", ""))[:240],
        "description": strip_html_text(course.get("description", "")),
        "page_url": f"https://aprende.org/cursos/view/{course.get('id')}",
        "site": "aprende.org",
        "source_url": source_url,
        "featured_image": course.get("imageUrl"),
        "imageUrl": course.get("imageUrl"),
        "categories": course.get("sector", {}).get("name") if isinstance(course.get("sector"), dict) else None,
        "external_link": f"https://aprende.org/cursos/view/{course.get('id')}",
        "raw_jsonld": json.dumps(course, ensure_ascii=False),
    }

    tags: List[str] = []
    for field in ("competences", "catalogs", "linkCourses"):
        values = course.get(field)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and item.get("name"):
                    tags.append(str(item["name"]))
                elif isinstance(item, str):
                    tags.append(item)
    if tags:
        record["tags"] = ", ".join(sorted(set(tags)))

    if course.get("difficultyId") is not None:
        record["level"] = str(course.get("difficultyId"))

    # include some simple numeric/stat fields when present
    for k in ("hitsCapacitate", "hitsAprende", "popularity", "videoId"):
        if course.get(k) is not None:
            record[k] = course.get(k)

    # If the API provides keywords or links, map them into tags/external fields
    if course.get("keywords"):
        if isinstance(course.get("keywords"), str):
            record.setdefault("tags", "")
            record["tags"] = ", ".join(sorted(set([t.strip() for t in course.get("keywords").split(",") if t.strip()])))

    if isinstance(course.get("links"), list) and course.get("links"):
        # try to extract first sensible URL
        urls: List[str] = []
        for item in course.get("links"):
            if isinstance(item, dict):
                u = item.get("url") or item.get("link") or item.get("href")
                if u:
                    urls.append(u)
            elif isinstance(item, str):
                urls.append(item)
        if urls:
            record["external_link"] = urls[0]

    return record
def scrape_aprende_org(start_url: str, fetch_details: bool = False) -> List[Dict[str, Any]]:
    # lightweight API listing; optionally call detail endpoint per-course if needed
    if requests is None:
        raise RuntimeError("The 'requests' package is required to scrape aprende.org.")
    def fetch_detail(course_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = requests.get(f"{APRRENDE_API_ROOT}/api/Courses/{int(course_id)}?platformId=2", headers=APRRENDE_API_HEADERS, timeout=15)
            if resp.status_code == 200:
                d = resp.json()
                return d if isinstance(d, dict) else None
        except Exception:
            return None
        return None

    url = f"{APRRENDE_API_ROOT}/api/Courses?platformId=2"
    response = requests.get(url, headers=APRRENDE_API_HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()
    courses = data.get("courses") or []
    records: List[Dict[str, Any]] = []
    for course in courses:
        if not isinstance(course, dict):
            continue
        detail = fetch_detail(course.get("id")) if fetch_details and course.get("id") else None
        merged = dict(course)
        if detail:
            merged.update(detail)
        record = extract_aprende_course_record(merged, start_url)
        normalized = normalize_course_record(record)
        if not any(r.get("Permalink") == normalized["Permalink"] for r in records):
            records.append(normalized)
    print(f"Found {len(records)} courses from aprende.org API")
    return records




def get_provider_for_url(url: str) -> Optional[str]:
    """Return provider key if URL matches a known provider, otherwise None."""
    # quick host-based checks for providers not registered in PROVIDERS
    try:
        hostname = urllib.parse.urlparse(url).netloc.lower()
        if "netacad.com" in hostname:
            return "netacad"
    except Exception:
        pass

    for key, entry in PROVIDERS.items():
        try:
            matcher = entry.get("matcher")
            if matcher and matcher(url):
                return key
        except Exception:
            continue
    return None


# Provider registry: map simple provider keys to matchers and scraper callables.
# Add new providers here as needed. Each entry supports keys:
# - "matcher": function(url)->bool to detect the site
# - "scraper": function(start_url, fetch_details=False)->List[Dict]
# - "supports_fetch_details": bool
PROVIDERS = {
    "aprende": {
        "matcher": is_aprende_site,
        "scraper": scrape_aprende_org,
        "supports_fetch_details": True,
    }
}

# register additional providers
    # The netacad provider registration has been removed to avoid referencing is_netacad_site before it's defined.


def is_netacad_site(url: str) -> bool:
    try:
        hostname = urllib.parse.urlparse(url).netloc.lower()
        return hostname.endswith("netacad.com") or hostname.endswith("www.netacad.com")
    except Exception:
        return False


def scrape_netacad(start_url: str, fetch_details: bool = False, render: bool = False) -> List[Dict[str, Any]]:
    """Simple scraper for a NetAcad course page. If start_url is a course page, return it; otherwise attempt to fetch a catalog listing.

    If `render` is True, the function will attempt to fetch pages using Playwright to render dynamic content.
    """
    # 'render' is a simple boolean that enables Playwright-based fetching for JS-driven pages.
    if requests is None:
        raise RuntimeError("The 'requests' package is required to scrape netacad.com.")

    records: List[Dict[str, Any]] = []
    try:
        html, final = fetch_html(start_url)
    except Exception as exc:
        print(f"Failed to fetch {start_url}: {exc}")
        return records

    # If rendering is requested and the initial fetch returned no in-document links,
    # try rendering the start page to pick up dynamic links.
    if render:
        try:
            rhtml, rfinal = render_fetch(start_url)
            # prefer rendered content if it provides more linkable content
            if rhtml and len(parse_links(rhtml, rfinal)) > len(parse_links(html, final)):
                html, final = rhtml, rfinal
        except ImportError as ie:
            print(str(ie))
        except Exception:
            pass

    final = final or start_url
    # If URL path looks like a course page, extract details directly.
    path = urllib.parse.urlparse(final).path or ""
    if "/courses/" in path or path.startswith("/courses"):
        page_data = extract_page_data(html, final, start_url)
        full_text = page_text(html)

        # labs
        labs_match = re.search(r"(\d+)\s+LABS", full_text, flags=re.I)
        if labs_match:
            page_data["labs"] = labs_match.group(1)

        # duration (try to capture patterns like 'FREE 6 HOURS' or '6 HOURS')
        dur_match = re.search(r"FREE\s*(\d+)\s*HOURS", full_text, flags=re.I)
        if not dur_match:
            dur_match = re.search(r"(\d+)\s*HOURS", full_text, flags=re.I)
        if dur_match:
            page_data["duration"] = dur_match.group(0)

        # level
        level_match = re.search(r"\b(BEGINNER|INTERMEDIATE|ADVANCED)\b", full_text, flags=re.I)
        if level_match:
            page_data["level"] = level_match.group(1).capitalize()

        # enrolled count
        enrolled = re.search(r"([\d,]+)\s+already enrolled", full_text, flags=re.I)
        if enrolled:
            page_data["enrolled"] = enrolled.group(1).replace(",", "")

        # ensure excerpt
        if "excerpt" not in page_data and page_data.get("description"):
            page_data["excerpt"] = page_data.get("description")[:240]

        record = {
            "id": None,
            "title": page_data.get("title"),
            "excerpt": page_data.get("excerpt", ""),
            "description": page_data.get("description", ""),
            "page_url": final,
            "site": "netacad.com",
            "featured_image": page_data.get("featured_image") or page_data.get("image"),
            "raw_jsonld": page_data.get("raw_jsonld", ""),
        }
        # merge detected fields
        for k in ("duration", "language", "level", "labs", "enrolled", "author", "tags"):
            if k in page_data:
                record[k] = page_data[k]

        normalized = normalize_course_record(record)
        records.append(normalized)
        return records

    # If not a course path, try to find catalog links (simple heuristic)
    links = parse_links(html, final)
    course_links: List[str] = []
    for l in links:
        if "/courses/" in l and l not in course_links:
            course_links.append(l)
        if len(course_links) >= 40:
            break

    # If none found on the landing page, try known catalog endpoints
    if not course_links:
        catalog_candidates = [
            urllib.parse.urljoin(final, "/catalogs/learn"),
            urllib.parse.urljoin(final, "/catalogs"),
            urllib.parse.urljoin(final, "/catalogs/learn?page=1"),
        ]
        for cat in catalog_candidates:
            try:
                ch, cf = fetch_html(cat)
            except Exception:
                continue
            for l in parse_links(ch, cf):
                if "/courses/" in l and l not in course_links:
                    course_links.append(l)
            if len(course_links) >= 40:
                break

    # If still none, try sitemaps (look for <loc> entries pointing to /courses/)
    if not course_links:
        for sitemap_path in ("/sitemap.xml", "/sitemap_index.xml"):
            sitemap_url = urllib.parse.urljoin(final, sitemap_path)
            try:
                stext, sfinal = fetch_html(sitemap_url)
            except Exception:
                continue
            for m in re.finditer(r"<loc>(https?://[^<]+)</loc>", stext, flags=re.I):
                loc = m.group(1).strip()
                if "/courses/" in loc and loc not in course_links:
                    course_links.append(loc)
            if len(course_links) >= 40:
                break

    for l in course_links:
        try:
            h, final_l = fetch_html(l)
        except Exception:
            continue
        page_data = extract_page_data(h, final_l, start_url)
        record = {"id": None, "title": page_data.get("title"), "excerpt": page_data.get("excerpt", ""), "page_url": final_l, "site": "netacad.com", "featured_image": page_data.get("featured_image", ""), "raw_jsonld": page_data.get("raw_jsonld", "")}
        normalized = normalize_course_record(record)
        if not any(r.get("Permalink") == normalized.get("Permalink") for r in records):
            records.append(normalized)
        if len(records) >= 80:
            break

    return records



def extract_page_data(html: str, url: str, source_url: str) -> Dict[str, Any]:
    page_data: Dict[str, Any] = {"source_url": source_url, "page_url": url, "site": urllib.parse.urlparse(source_url).netloc}
    meta = parse_meta(html)
    jsonld_blocks = find_jsonld(html)

    if meta.get("og:title"):
        page_data["title"] = meta["og:title"]
    elif meta.get("title"):
        page_data["title"] = meta["title"]
    elif meta.get("twitter:title"):
        page_data["title"] = meta["twitter:title"]

    if meta.get("description"):
        page_data["description"] = meta["description"]
    elif meta.get("og:description"):
        page_data["description"] = meta["og:description"]
    elif meta.get("twitter:description"):
        page_data["description"] = meta["twitter:description"]

    if meta.get("og:image"):
        page_data["featured_image"] = meta["og:image"]
    elif meta.get("twitter:image"):
        page_data["featured_image"] = meta["twitter:image"]

    if jsonld_blocks:
        page_data["raw_jsonld"] = json.dumps(jsonld_blocks, ensure_ascii=False)
        for block in jsonld_blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("@type") or block.get("type")
            if isinstance(block_type, list):
                block_type = block_type[0]
            if block_type and str(block_type).lower() == "course":
                page_data["title"] = page_data.get("title") or block.get("name")
                page_data["description"] = page_data.get("description") or block.get("description")
                page_data["author"] = page_data.get("author") or json.dumps(block.get("author", {}), ensure_ascii=False)
                if block.get("offers"):
                    offers = block["offers"]
                    if isinstance(offers, dict):
                        page_data["price"] = offers.get("price") or page_data.get("price")
                        page_data["free"] = "yes" if str(offers.get("price", "")).strip() in ["0", "0.0", "0.00", "free", "gratis"] else page_data.get("free")
                if block.get("provider"):
                    page_data["external_link"] = block.get("provider", {}).get("url") or page_data.get("external_link")
                if block.get("inLanguage") and not page_data.get("language"):
                    page_data["language"] = block.get("inLanguage")
                if block.get("timeRequired") and not page_data.get("duration"):
                    page_data["duration"] = block.get("timeRequired")
            if block_type and str(block_type).lower() in ["itemlist", "webpage"] and block.get("mainEntity"):
                main = block["mainEntity"]
                if isinstance(main, dict) and main.get("@type", "").lower() == "course":
                    page_data["title"] = page_data.get("title") or main.get("name")
                    page_data["description"] = page_data.get("description") or main.get("description")
    full_text = page_text(html)
    page_data.update(find_course_fields(full_text))

    if "excerpt" not in page_data and page_data.get("description"):
        page_data["excerpt"] = page_data["description"][:240]
    elif "excerpt" not in page_data:
        page_data["excerpt"] = full_text[:240]

    if "title" not in page_data:
        title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I | re.S)
        if title_match:
            page_data["title"] = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

    return page_data


def score_course_page(html: str, url: str) -> int:
    score = 0
    text = page_text(html).lower()

    # keyword matches (broad)
    if any(keyword in text for keyword in COURSE_KEYWORDS):
        score += 2
    if re.search(r"\bcurso\b", text):
        score += 3
    if re.search(r"\bcertificaci[oó]n\b", text):
        score += 2

    # JSON-LD Course detection
    jsonld = find_jsonld(html)
    if any((isinstance(block, dict) and str(block.get("@type", "")).lower() == "course") for block in jsonld):
        score += 8

    # Microdata / itemtype detection for schema.org Course
    if re.search(r"schema\.org\/(Course|course)\b|itemtype=[\"']?https?:\\/\\/schema\.org\\/Course", html, flags=re.I):
        score += 8

    # Class or id attributes that suggest course cards or course lists
    if re.search(r"(class|id)=[\"'][^\"']*(course|course-card|course-item|course-list|training|lesson|module)[^\"']*[\"']", html, flags=re.I):
        score += 2

    # Enrollment / CTA words
    if any(w in text for w in ("enroll", "register", "inscrib", "sign up", "signup", "buy", "add to cart")):
        score += 2

    # presence of duration words
    if re.search(r"\b(hours|hour|hrs|minutes|min)\b", text):
        score += 1

    # URL hints
    low_url = (url or "").lower()
    if low_url and ("/curso" in low_url or "/curso/" in low_url):
        score += 2
    if low_url and ("/course" in low_url or "/courses" in low_url or "/course/" in low_url):
        score += 1

    return score


def normalize_course_record(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in record.items():
        if key == "description":
            continue
        if key in FIELD_MAP:
            normalized_key = FIELD_MAP[key]
        else:
            normalized_key = key

        if normalized_key == "Excerpt" and key == "description" and record.get("excerpt"):
            continue

        normalized[normalized_key] = value

    if "Permalink" not in normalized and record.get("page_url"):
        normalized["Permalink"] = record["page_url"]
    if "Excerpt" not in normalized and record.get("excerpt"):
        normalized["Excerpt"] = record["excerpt"]

    for header in OUTPUT_FIELDS:
        if header not in normalized:
            normalized[header] = ""
    return normalized


def choose_output_headers(records: List[Dict[str, Any]]) -> List[str]:
    headers: List[str] = OUTPUT_FIELDS[:]
    additional: List[str] = []
    for record in records:
        for key in record:
            if key not in headers and key not in additional:
                additional.append(key)
    return headers + sorted(additional)


def write_csv(records: List[Dict[str, Any]], output_path: str) -> None:
    if not records:
        print("No course records were found. No CSV file was created.")
        return
    headers = choose_output_headers(records)
    with open(output_path, "w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in headers}
            writer.writerow(row)
    print(f"Saved {len(records)} records to {output_path}")


def crawl_site(
    start_url: str,
    max_pages: int = 200,
    max_course_pages: int = 100,
    provider: Optional[str] = None,
    fetch_details: bool = False,
    render: bool = False,
) -> List[Dict[str, Any]]:
    # Provider-specific scraping (APIs or tailored scrapers)
    provider_key = provider
    if not provider_key:
        provider_key = get_provider_for_url(start_url)

    if provider_key and provider_key in PROVIDERS:
        entry = PROVIDERS[provider_key]
        scraper = entry.get("scraper")
        supports_fetch = bool(entry.get("supports_fetch_details"))
        try:
            if scraper:
                if supports_fetch:
                    return scraper(start_url, fetch_details=fetch_details)
                else:
                    # many scrapers accept render optional param, pass if available
                    try:
                        return scraper(start_url, fetch_details=fetch_details, render=render)
                    except TypeError:
                        return scraper(start_url)
        except Exception as exc:
            print(f"Provider '{provider_key}' scrape failed: {exc}")
            print("Falling back to generic HTML crawling.")
    # Handle some known providers even if not registered in PROVIDERS
    if provider_key == "netacad" and "scrape_netacad" in globals():
        try:
            return scrape_netacad(start_url, fetch_details=fetch_details, render=render)
        except Exception as exc:
            print(f"NetAcad scrape failed: {exc}")
            print("Falling back to generic HTML crawling.")

    visited: Set[str] = set()
    queue = deque([start_url])
    course_records: List[Dict[str, Any]] = []
    domain = urllib.parse.urlparse(start_url).netloc.lower()
    page_count = 0

    while queue and page_count < max_pages and len(course_records) < max_course_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        page_count += 1
        try:
            html, final_url = fetch_html(url)
        except Exception as exc:
            print(f"Failed to fetch {url}: {exc}")
            continue

        final_url = final_url or url
        if final_url != url and final_url in visited:
            continue
        current_url = final_url
        if current_url not in visited:
            visited.add(current_url)

        if not same_domain(current_url, start_url):
            continue

        links = parse_links(html, final_url)
        for href in links:
            if same_domain(href, start_url) and href not in visited and href not in queue:
                queue.append(href)

        score = score_course_page(html, final_url)
        if score >= 3:
            data = extract_page_data(html, final_url, start_url)
            if data and any(data.get(field) for field in ["title", "description", "excerpt"]):
                normalized_data = normalize_course_record(data)
                if not any(r.get("Permalink") == normalized_data["Permalink"] for r in course_records):
                    course_records.append(normalized_data)
                    print(f"Found course page: {normalized_data.get('Title','(no title)')} -> {final_url} (score {score})")

    return course_records


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape course information from a website and export it to CSV.")
    parser.add_argument("url", nargs="?", help="The website URL to scrape.")
    parser.add_argument("--output", "-o", help="CSV output file path.")
    parser.add_argument("--max-pages", type=int, default=120, help="Maximum number of pages to crawl.")
    parser.add_argument("--max-courses", type=int, default=80, help="Maximum number of course pages to collect.")
    parser.add_argument("--provider", type=str, default=None, help="Optional provider key to force (e.g. 'aprende').")
    parser.add_argument("--fetch-details", action="store_true", help="When supported, fetch per-course details from provider APIs (may be slow).")
    parser.add_argument("--render", action="store_true", help="Render pages with a headless browser (Playwright) to extract dynamic links. Requires Playwright installed.")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    start_url = args.url or input("Enter the website URL to scrape: ").strip()
    if not start_url:
        print("A website URL is required.")
        return 1
    if not start_url.startswith("http"):
        start_url = "https://" + start_url

    output_path = args.output
    if not output_path:
        domain = urllib.parse.urlparse(start_url).netloc.replace(".", "_")
        output_path = f"courses_{domain}_{int(time.time())}.csv"

    if requests is None or BeautifulSoup is None:
        print("WARNING: The script works best with the 'requests' and 'beautifulsoup4' packages installed.")
        print("Install them with: pip install requests beautifulsoup4")

    provider_arg = getattr(args, "provider", None)
    detected_provider = provider_arg or get_provider_for_url(start_url)
    records = crawl_site(
        start_url,
        max_pages=args.max_pages,
        max_course_pages=args.max_courses,
        provider=provider_arg,
        fetch_details=getattr(args, "fetch_details", False),
        render=getattr(args, "render", False),
    )
    if not records:
        if detected_provider == "netacad":
            print("No course records were found. NetAcad's site uses dynamic rendering and the crawler could not discover course links from the site root.")
            print("Options: 1) Provide a specific course or catalog URL (e.g. 'https://www.netacad.com/courses/...'), 2) Re-run with --render after installing Playwright (pip install playwright; playwright install).")
        else:
            print("No course records were found. Try giving a more specific start URL (a course or catalog page) or use --render for JS-driven sites.")
    write_csv(records, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
