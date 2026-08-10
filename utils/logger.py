import logging
import sys
from config import config


def _build_handler():
    stream = None
    if getattr(sys, "stdout", None) is not None:
        stream = sys.stdout
    elif getattr(sys, "stderr", None) is not None:
        stream = sys.stderr

    if stream is None:
        return logging.NullHandler()

    handler = logging.StreamHandler(stream=stream)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    return handler


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = _build_handler()
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    return logger

import datetime

def log_run_summary(url: str, output: str, provider: str, render: bool, courses_count: int, error: str = None):
    """
    Writes an incremental summary of a scraper run to a local log file.
    """
    log_file = "scraper_runs.log"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if not error else "FAILED"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now}] RUN {status}\n")
        f.write(f"  URL: {url}\n")
        f.write(f"  Provider: {provider or 'Generic'}\n")
        f.write(f"  Render Mode: {render}\n")
        f.write(f"  Output File: {output}\n")
        f.write(f"  Extracted Courses: {courses_count}\n")
        if error:
            f.write(f"  Error: {error}\n")
        f.write("-" * 40 + "\n")
