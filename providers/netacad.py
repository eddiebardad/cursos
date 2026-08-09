from typing import Iterator, List, Optional
import urllib.parse
import re
from .base import ProviderBase
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

# Canonical sitemap URL — returns real XML without JS rendering
_SITEMAP_URL = "https://www.netacad.com/sitemap.xml"

# Known catalog/listing paths to try when rendering (JS needed)
_CATALOG_CANDIDATES = [
    "/catalogs/learn?category=course",
    "/catalogs/learn",
]


class NetacadProvider(ProviderBase):
    provider_name = "Netacad"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        netloc = urllib.parse.urlparse(url).netloc
        return "netacad.com" in netloc

    def should_crawl(self, url: str) -> bool:
        return False   # We control crawling entirely in scrape()

    def scrape(self, url: str, render: bool = False) -> Iterator[Course]:
        engine = "Playwright" if render else "Sitemap (static)"
        logger.info(f"Scraping Netacad | Strategy: {engine}")

        path = urllib.parse.urlparse(url).path or ""

        # A real course detail page has a slug after /courses/, e.g. /courses/python-essentials-1
        # Listing pages like /courses/all-courses are NOT detail pages
        is_course_detail = bool(re.search(r"/courses/[^/]+/?$", path)) and "all-courses" not in path

        # ── Direct course page ──────────────────────────────────────────────────
        if is_course_detail:
            html = self._fetch_html(url, render=render)
            if html:
                course = self._extract_course(html, url)
                if course:
                    yield course
            return


        # ── Catalog / listing page ──────────────────────────────────────────────
        course_links = []

        if render:
            # Playwright: render the catalog SPA and harvest all /courses/ links
            html = self._fetch_html(url, render=True)
            if html:
                course_links = self._course_links_from_html(html, url)

            # If the rendered catalog didn't surface links, try known paths
            if not course_links:
                origin = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
                for path_candidate in _CATALOG_CANDIDATES:
                    chtml = self._fetch_html(origin + path_candidate, render=True)
                    if chtml:
                        course_links = self._course_links_from_html(chtml, origin + path_candidate)
                    if course_links:
                        break

            if not course_links:
                logger.warning("Could not find course links on NetAcad catalog pages even with rendering.")
                return

            logger.info(f"Found {len(course_links)} course links. Scraping each…")
            seen: set = set()
            for link in course_links:
                if link in seen:
                    continue
                seen.add(link)
                try:
                    chtml = self._fetch_html(link, render=True)
                    if not chtml:
                        continue
                    course = self._extract_course(chtml, link)
                    if course:
                        yield course
                except Exception as e:
                    logger.warning(f"Failed to scrape {link}: {e}")
        else:
            # Static mode: build Course records from sitemap URLs only.
            # NetAcad's course detail pages (cperf.netacad.com) block bots with 403,
            # so we construct minimal records from the slug and canonical URL pattern.
            logger.info(
                "Static mode: building course list from sitemap slugs. "
                "Use --render for full course details."
            )
            course_links = self._course_links_from_sitemap(_SITEMAP_URL)
            if not course_links:
                logger.warning("No course URLs found in NetAcad sitemap.")
                return
            for link in course_links:
                slug = link.rstrip("/").split("/")[-1]
                # Construct the public-facing URL on www.netacad.com
                public_url = f"https://www.netacad.com/courses/{slug}"
                name = slug.replace("-", " ").title()
                from schemas.models import Course as CourseModel
                try:
                    course = CourseModel(
                        name=name,
                        url=public_url,
                        provider=self.provider_name,
                    )
                    yield course
                except Exception as e:
                    logger.warning(f"Could not build course for slug '{slug}': {e}")

    # ───────────────────────────── Private helpers ─────────────────────────────

    def _fetch_html(self, url: str, render: bool = False) -> Optional[str]:
        try:
            return self.crawler.get(url, render=render)
        except Exception as e:
            logger.error(f"Fetch failed for {url}: {e}")
            return None

    def _course_links_from_sitemap(self, sitemap_url: str) -> List[str]:
        """Parse the XML sitemap and return all /courses/ URLs."""
        html = self._fetch_html(sitemap_url, render=False)
        if not html:
            return []
        links = []
        for m in re.finditer(r"<loc>(https?://[^<]+)</loc>", html, flags=re.I):
            loc = m.group(1).strip()
            if "/courses/" in loc:
                links.append(loc)
        logger.info(f"Sitemap yielded {len(links)} course URLs.")
        return links

    def _course_links_from_html(self, html: str, base_url: str) -> List[str]:
        """Extract /courses/* links from a rendered HTML page."""
        from core.parser import Parser
        soup = Parser.parse_html(html)
        all_links = Parser.extract_internal_links(soup, base_url)
        return [l for l in all_links if "/courses/" in l]

    def _extract_course(self, html: str, url: str) -> Optional[Course]:
        """Parse a course detail page into a Course model."""
        course = self.parser.parse_course_page(html, url)

        if not course:
            from core.parser import Parser
            soup = Parser.parse_html(html)
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else url
            og_desc = soup.find("meta", property="og:description")
            desc = og_desc.get("content") if og_desc else None
            og_img = soup.find("meta", property="og:image")
            img = og_img.get("content") if og_img else None
            from schemas.models import Course as CourseModel
            try:
                course = CourseModel(name=title, url=url, description=desc, image=img)
            except Exception:
                return None

        if course:
            course.provider = self.provider_name
            # Enrich with heuristic text mining
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)

            if not course.timeRequired:
                dur = re.search(r"(\d+)\s*HOURS?", text, flags=re.I)
                if dur:
                    course.timeRequired = f"PT{dur.group(1)}H"

            if not course.educationalLevel:
                lvl = re.search(r"\b(BEGINNER|INTERMEDIATE|ADVANCED)\b", text, flags=re.I)
                if lvl:
                    course.educationalLevel = lvl.group(1).capitalize()

        return course
