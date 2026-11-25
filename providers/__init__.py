import importlib
import pkgutil
import re

from .base import ProviderBase

# Auto-import all modules in this package so their __init_subclass__ runs
for module_info in pkgutil.iter_modules(__path__):
    importlib.import_module(f".{module_info.name}", package=__name__)

def get_provider_for_url(url: str) -> ProviderBase | None:
    """Find and instantiate the first provider that can handle the URL."""
    for provider_cls in ProviderBase._registry:
        if provider_cls.can_handle(url):
            return provider_cls()
    return None

def get_provider_by_name(name: str) -> ProviderBase | None:
    """Find and instantiate a provider explicitly by its class or provider_name."""
    name_normalized = _normalize_provider_name(name)
    for provider_cls in ProviderBase._registry:
        registered_names = {
            _normalize_provider_name(provider_cls.provider_name),
            _normalize_provider_name(provider_cls.__name__),
            *(
                _normalize_provider_name(alias)
                for alias in provider_cls.provider_aliases
            ),
        }
        if name_normalized in registered_names:
            return provider_cls()
    return None


def _normalize_provider_name(name: str) -> str:
    return re.sub(r"[\s_-]+", "", name).casefold()
