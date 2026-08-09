from abc import ABC, abstractmethod
from typing import Iterator
from schemas.models import Course
from core.crawler import Crawler
from core.parser import Parser

class ProviderBase(ABC):
    """
    Abstract Base Class for all site-specific adapters.
    Automatically registers subclasses into the Provider Registry.
    """
    provider_name = "Base"
    
    # Registry to store all adapter subclasses
    _registry = []
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.provider_name != "Base":
            ProviderBase._registry.append(cls)

    def __init__(self):
        self.crawler = Crawler()
        self.parser = Parser()

    @classmethod
    @abstractmethod
    def can_handle(cls, url: str) -> bool:
        """Return True if this adapter can handle the given URL domain."""
        pass
        
    def should_crawl(self, url: str) -> bool:
        """Hook for crawler to decide if a URL should be visited."""
        return True

    @abstractmethod
    def scrape(self, url: str, render: bool = False) -> Iterator[Course]:
        """Fetch the page and yield normalized Course records."""
        pass

    # --- Helper Stubs for Subclasses ---
    
    def _extract_via_api(self, api_url: str) -> dict:
        """Helper for fetching hidden API data on dynamic sites."""
        pass
        
    def _parse_custom_selectors(self, html: str) -> dict:
        """Helper for using BeautifulSoup to find site-specific DOM elements."""
        pass
