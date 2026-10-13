"""Logging helpers that keep document data out of logs (§0.2).

Messages of unexpected exceptions can contain file paths or document text, so
they are logged as the exception type plus code locations only.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import PurePath

__all__ = ["log_unexpected"]


def log_unexpected(logger: logging.Logger, exc: BaseException, context: str) -> None:
    frames = traceback.extract_tb(exc.__traceback__)[-6:]
    where = " <- ".join(
        f"{PurePath(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames)
    )
    logger.error("%s: unexpected %s at %s", context, type(exc).__name__, where or "?")
