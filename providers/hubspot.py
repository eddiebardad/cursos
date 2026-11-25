import urllib.parse
from collections.abc import Iterator

from schemas.models import Course
from utils.logger import get_logger

from .base import ProviderBase

logger = get_logger(__name__)

class HubspotProvider(ProviderBase):
    provider_name = "HubspotAcademy"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "academy.hubspot.com" in urllib.parse.urlparse(url).netloc

    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        logger.info(f"Scraping {self.provider_name} URL: {url}")

        html = self.crawler.get(url, render=render)
        course = self.parser.parse_course_page(html, url)

        if course:
            data = course.model_dump()
            data["provider"] = self.provider_name
            try:
                yield Course.model_validate(data)
            except Exception:
                yield course
