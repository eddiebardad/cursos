from typing import Iterator, Optional
import urllib.parse
from .base import ProviderBase
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

# Real backend for aprende.org
_API_ROOT = "https://besvc.capacitateparaelempleo.org"
_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Course Scraper)",
    "includeHATEOAS": "N",
    "platformId": "2",
    "x-languageCode": "es",
    "x-isApp": "false",
    "X-API-KEY": "",
}


class AprendeProvider(ProviderBase):
    provider_name = "Aprende"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "aprende.org" in urllib.parse.urlparse(url).netloc

    def should_crawl(self, url: str) -> bool:
        # Never let the generic BFS crawler loose on aprende.org;
        # we handle everything through their private API directly.
        return False

    def scrape(self, url: str, render: bool = False) -> Iterator[Course]:
        """Fetch the full course catalogue from the Aprende.org backend API."""
        logger.info(f"Fetching full course list from {_API_ROOT}/api/Courses?platformId=2")
        try:
            raw = self.crawler.get(
                f"{_API_ROOT}/api/Courses?platformId=2",
                headers=_API_HEADERS,
            )
        except Exception as e:
            logger.error(f"Failed to reach Aprende API: {e}")
            return

        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Aprende API returned invalid JSON: {e}")
            return

        courses = data.get("courses") or []
        if not courses:
            logger.warning("Aprende API returned zero courses.")
            return

        logger.info(f"Aprende API returned {len(courses)} courses. Normalising…")
        seen_ids = set()
        for item in courses:
            if not isinstance(item, dict):
                continue
            course_id = item.get("id")
            if course_id in seen_ids:
                continue
            seen_ids.add(course_id)

            course = self._map_to_course(item)
            if course:
                yield course

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_detail(self, course_id: int) -> Optional[dict]:
        """Fetch the per-course detail endpoint (optional enrichment)."""
        try:
            raw = self.crawler.get(
                f"{_API_ROOT}/api/Courses/{int(course_id)}?platformId=2",
                headers=_API_HEADERS,
            )
            import json
            d = json.loads(raw)
            return d if isinstance(d, dict) else None
        except Exception:
            return None

    @staticmethod
    def _parse_course_page(html: str, url: str) -> dict:
        """Extract additional data from HTML page if needed (BeautifulSoup fallback)."""
        from core.parser import Parser
        soup = Parser.parse_html(html)
        json_lds = Parser.extract_json_ld(soup)
        return json_lds[0] if json_lds else {}

    def _map_to_course(self, item: dict) -> Optional[Course]:
        """Map a raw API response dict to the standard Course Pydantic model."""
        import html as html_module
        import re

        def _strip(value: str) -> str:
            return html_module.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()

        course_id = item.get("id")
        permalink = f"https://aprende.org/cursos/view/{course_id}" if course_id else None

        # Categories / keywords from nested structures
        tags = []
        for field in ("competences", "catalogs", "linkCourses"):
            values = item.get(field)
            if isinstance(values, list):
                for v in values:
                    if isinstance(v, dict) and v.get("name"):
                        tags.append(str(v["name"]))
                    elif isinstance(v, str):
                        tags.append(v)

        # Difficulty → educationalLevel
        difficulty_map = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}
        edu_level = difficulty_map.get(item.get("difficultyId")) or str(item.get("difficultyId")) if item.get("difficultyId") else None

        # Sector → categories
        sector = item.get("sector")
        category = sector.get("name") if isinstance(sector, dict) else None

        try:
            return Course(
                name=_strip(item.get("name", "")),
                description=_strip(item.get("description", "")),
                url=permalink,
                image=item.get("imageUrl"),
                provider=self.provider_name,
                inLanguage="es",
                isAccessibleForFree=True,
                price=0.0,
                priceCurrency="USD",
                offerUrl=permalink,
                educationalLevel=edu_level,
                keywords=tags if tags else None,
                about=category,
                # dcterms:identifier from the API id
            )
        except Exception as e:
            logger.warning(f"Could not create Course for id={course_id}: {e}")
            return None
