import importlib
import logging
from typing import Optional

from .base import ProviderBase

logger = logging.getLogger(__name__)


def _load_provider_modules() -> None:
    """Ensure provider modules are imported so their subclasses register themselves."""
    if ProviderBase._registry:
        return

    for module_name in ("aprende", "cognitiveclass", "hubspot", "netacad"):
        try:
            importlib.import_module(f".{module_name}", package=__name__)
        except Exception as exc:  # pragma: no cover - defensive for frozen builds
            logger.debug("Unable to load provider module %s: %s", module_name, exc)


_load_provider_modules()


def get_provider_for_url(url: str) -> Optional[ProviderBase]:
    """Find and instantiate the first provider that can handle the URL."""
    _load_provider_modules()
    for provider_cls in ProviderBase._registry:
        if provider_cls.can_handle(url):
            return provider_cls()
    return None


def get_provider_by_name(name: str) -> Optional[ProviderBase]:
    """Find and instantiate a provider explicitly by its class or provider_name."""
    _load_provider_modules()
    name_lower = name.lower()
    for provider_cls in ProviderBase._registry:
        if provider_cls.provider_name.lower() == name_lower or provider_cls.__name__.lower() == name_lower:
            return provider_cls()
    return None
