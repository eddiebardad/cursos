"""
config.py
==============================================================================
Configuración centralizada de Cursodex (v0.4.1).
Valores por defecto respetando los acuerdos arquitectónicos y sobreescribibles
mediante variables de entorno.
==============================================================================
"""

import os


class Config:
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HTTP_TIMEOUT: float = float(os.getenv("HTTP_TIMEOUT", "30.0"))
    COURTESY_DELAY: float = float(os.getenv("COURTESY_DELAY", "1.0"))
    FOLLOW_REDIRECTS: bool = os.getenv("FOLLOW_REDIRECTS", "True").lower() in ("true", "1", "yes")
    MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "0"))
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "CursodexBot/1.0 (+https://cursodex.com; academic research index)",
    )


config = Config()
