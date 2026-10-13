"""Locate documents shipped with the application (help, licences) — §6.8.

Order: inside the package (wheel / installer), next to a frozen executable,
then the source checkout (development).
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["find_doc"]

_PACKAGE_DOCS = Path(__file__).resolve().parent / "resources" / "docs"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def find_doc(name: str) -> Path | None:
    candidates = [_PACKAGE_DOCS / name]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "docs" / name)
    candidates += [_REPO_ROOT / "docs" / name, _REPO_ROOT / name]
    return next((p for p in candidates if p.is_file()), None)
