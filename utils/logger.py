"""
utils/logger.py
==============================================================================
Logger centralizado de Cursodex.

REGLAS INQUEBRANTABLES:
1. El 100% de los logs y advertencias se envían exclusivamente a sys.stderr.
2. Cero escrituras a archivos .log en disco (compatible con contenedor sin estado).
3. emit_run_summary emite una única línea JSON compacta al final de la ejecución
   directamente a sys.stderr con la estructura requerida en ARCHITECTURE.md §3.
==============================================================================
"""

import json
import logging
import sys
from datetime import UTC, datetime

from config import config

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene o configura un logger de forma idempotente enviando 100% a sys.stderr.
    """
    logger = logging.getLogger(name)

    # Verificar si ya tiene un StreamHandler apuntando a sys.stderr
    has_stderr_handler = any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in logger.handlers
    )

    if not has_stderr_handler:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_FORMATTER)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    logger.propagate = False
    return logger


def emit_run_summary(
    provider: str | None,
    url: str | None,
    courses_extracted: int,
    needs_review_count: int,
    exit_code: int,
    elapsed_seconds: float,
) -> None:
    """
    Emite un resumen estructurado de la ejecución en una única línea JSON compacta
    a sys.stderr (ARCHITECTURE.md §3).
    """
    summary = {
        "event": "run_summary",
        "provider": provider,
        "url": url,
        "courses_extracted": courses_extracted,
        "needs_review_count": needs_review_count,
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    sys.stderr.write(json.dumps(summary, ensure_ascii=False) + "\n")
    sys.stderr.flush()
