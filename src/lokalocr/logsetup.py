"""Logging configuration: rotating file in the user's log folder (§7.5 Zaawansowane).

Log records contain metadata only (sizes, page counts, timings, error codes);
callers never pass document text or file names (§0.2).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lokalocr import config

__all__ = ["LEVELS", "configure"]

LEVELS = {"warning": logging.WARNING, "info": logging.INFO, "debug": logging.DEBUG}
_HANDLER_NAME = "lokalocr-file"


def configure(level: str = "warning", directory: Path | None = None) -> Path | None:
    """(Re)configure the ``lokalocr`` logger. Returns the log file, if file logging works."""
    logger = logging.getLogger("lokalocr")
    logger.setLevel(LEVELS.get(level, logging.WARNING))
    for handler in list(logger.handlers):
        if handler.get_name() == _HANDLER_NAME:
            logger.removeHandler(handler)
            handler.close()
    target_dir = directory or config.log_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "lokalocr.log"
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return path
