"""Application temporary folder (§6.5).

Everything the app may need to spill to disk while working lives in one
per-user folder that is wiped at start-up (leftovers after a crash) and at
exit. Nothing in it survives the application.
"""

from __future__ import annotations

import contextlib
import getpass
import logging
import re
import shutil
import tempfile
from pathlib import Path

__all__ = ["app_temp_dir", "cleanup", "default_root", "set_root"]

_log = logging.getLogger(__name__)
_root: Path | None = None


def default_root() -> Path:
    try:
        user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser())
    except Exception:
        user = "user"
    return Path(tempfile.gettempdir()) / f"LokalOCR-{user}"


def set_root(path: Path | None) -> None:
    """Use a custom folder (from settings); ``None`` restores the default."""
    global _root
    _root = path


def app_temp_dir() -> Path:
    root = _root or default_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup() -> bool:
    """Remove the temp folder's contents. Returns ``True`` if it is now empty."""
    root = _root or default_root()
    if not root.exists():
        return True
    failures = 0
    for child in root.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError:
            failures += 1
    if failures:
        _log.warning("Temporary folder cleanup left %d entries", failures)
    with contextlib.suppress(OSError):
        root.rmdir()
    return failures == 0
