from typing import Iterator
import urllib.parse
from .base import ProviderBase
from schemas.models import Course
from utils.logger import get_logger

logger = get_logger(__name__)

class CognitiveClassProvider(ProviderBase):
    provider_name = "CognitiveClass"

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return "cognitiveclass.ai" in urllib.parse.urlparse(url).netloc

    def scrape(self, url: str, render: bool = False) -> Iterator[Course]:
        logger.info(f"Scraping {self.provider_name} URL: {url}")
        
        html = self.crawler.get(url, render=render)
        course = self.parser.parse_course_page(html, url)
        
        if course:
            course.provider = self.provider_name
            yield course
        else:
            pass
