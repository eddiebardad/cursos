import json
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup
from pydantic import ValidationError

from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

class Parser:
    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
        results = []
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            if script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        results.extend(data)
                    else:
                        results.append(data)
                except json.JSONDecodeError:
                    pass
        return results

    @staticmethod
    def extract_internal_links(soup: BeautifulSoup, base_url: str) -> list[str]:
        parsed_base = urllib.parse.urlparse(base_url)
        base_domain = parsed_base.netloc

        links = []
        for a_tag in soup.find_all("a", href=True):
            href = str(a_tag["href"])
            full_url = urllib.parse.urljoin(base_url, href)
            parsed_url = urllib.parse.urlparse(full_url)

            if parsed_url.netloc == base_domain:
                clean_url = urllib.parse.urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, parsed_url.query, ''))
                links.append(clean_url)

        return list(set(links))

    @staticmethod
    def detect_course_page(soup: BeautifulSoup) -> bool:
        # 1. Check JSON-LD
        json_lds = Parser.extract_json_ld(soup)
        for data in json_lds:
            item_type = data.get("@type", "")
            if isinstance(item_type, str) and item_type == "Course":
                return True
            if isinstance(item_type, list) and "Course" in item_type:
                return True

        # 2. Check Microdata
        if soup.find(attrs={"itemtype": "http://schema.org/Course"}):  # type: ignore[call-overload]
            return True

        # 3. Check OpenGraph / Heuristics
        og_type = soup.find("meta", property="og:type")
        if og_type and og_type.get("content") in ["course", "education"]:
            return True

        return False

    @staticmethod
    def parse_course_page(html: str, url: str) -> Course | None:
        soup = Parser.parse_html(html)
        if not Parser.detect_course_page(soup):
            return None

        json_lds = Parser.extract_json_ld(soup)
        for data in json_lds:
            item_type = data.get("@type", "")
            is_course = (isinstance(item_type, str) and item_type == "Course") or (isinstance(item_type, list) and "Course" in item_type)
            if is_course:
                name = str(data.get("name") or (soup.title.string if soup.title else "") or "")
                description = data.get("description")

                provider_data = data.get("provider", {})
                provider_name = provider_data.get("name") if isinstance(provider_data, dict) else provider_data

                isAccessibleForFree = data.get("isAccessibleForFree")

                inLanguage = data.get("inLanguage")
                educationalLevel = data.get("educationalLevel")
                timeRequired = data.get("timeRequired")
                about = data.get("about")

                keywords = data.get("keywords", [])
                if isinstance(keywords, str):
                    keywords = [k.strip() for k in keywords.split(",")]

                image = data.get("image")
                if isinstance(image, list):
                    image = image[0]
                if isinstance(image, dict):
                    image = image.get("url")

                try:
                    return Course(
                        name=name,
                        url=url,
                        description=description,
                        provider=provider_name,
                        is_accessible_for_free=isAccessibleForFree if isAccessibleForFree is not None else True,
                        in_language=inLanguage,
                        educational_level=educationalLevel,
                        time_required=timeRequired,
                        category=about,
                        keywords=keywords,
                        image=image,
                    )
                except ValidationError as e:
                    logger.warning(f"Validation error for {url}: {e}")
                    pass

        # Fallback to OG/HTML Heuristics
        og_title = soup.find("meta", property="og:title")
        title = str(og_title.get("content", "")) if og_title else str(soup.title.string if soup.title else "Unknown Course")

        og_desc = soup.find("meta", property="og:description")
        desc = str(og_desc.get("content", "")) if og_desc else None

        # Normalize visible page text as a fallback
        if not desc:
            paragraphs = soup.find_all("p")
            if paragraphs:
                visible_text = " ".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                desc = visible_text[:500] + "..." if len(visible_text) > 500 else visible_text

        og_image = soup.find("meta", property="og:image")
        image = str(og_image.get("content", "")) if og_image else None

        try:
            return Course(
                name=title,
                url=url,
                description=desc,
                image=image
            )
        except ValidationError:
            return None

def parse_course_page(html: str, url: str) -> Course | None:
    return Parser.parse_course_page(html, url)
