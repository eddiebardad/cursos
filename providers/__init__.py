import importlib
import pkgutil
from typing import Optional
from .base import ProviderBase

# Auto-import all modules in this package so their __init_subclass__ runs
for _, module_name, _ in pkgutil.iter_modules(__path__):
    importlib.import_module(f".{module_name}", package=__name__)

def get_provider_for_url(url: str) -> Optional[ProviderBase]:
    """Find and instantiate the first provider that can handle the URL."""
    for provider_cls in ProviderBase._registry:
        if provider_cls.can_handle(url):
            return provider_cls()
    return None

def get_provider_by_name(name: str) -> Optional[ProviderBase]:
    """Find and instantiate a provider explicitly by its class or provider_name."""
    name_lower = name.lower()
    for provider_cls in ProviderBase._registry:
        if provider_cls.provider_name.lower() == name_lower or provider_cls.__name__.lower() == name_lower:
            return provider_cls()
    return None
