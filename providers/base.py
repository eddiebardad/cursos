"""
providers/base.py
==============================================================================
Clase Base Abstracta para adaptadores de proveedores de cursos.
Incluye registro automático de subclases y atributos de contrato.
==============================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from core.crawler import Crawler
from core.parser import Parser
from schemas.models import Course


class ProviderBase(ABC):
    """
    Abstract Base Class for all site-specific adapters.
    Automatically registers subclasses into the Provider Registry.
    """

    provider_name: str = "Base"
    default_url: str | None = None  # URL de entrada por defecto para el proveedor

    # Registry to store all adapter subclasses
    _registry: ClassVar[list[type[ProviderBase]]] = []

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
    def scrape(
        self,
        url: str,
        render: bool = False,
        limit: int = 0,
        enable_modules: bool = False,
    ) -> Iterator[Course]:
        """Fetch the page and yield normalized Course records."""
        pass
