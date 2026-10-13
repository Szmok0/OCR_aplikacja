"""Plain-text export (UTF-8, no BOM; CRLF line endings on Windows for Notepad users)."""

from __future__ import annotations

import sys
from pathlib import Path

from lokalocr.exporters.common import write_atomic
from lokalocr.model import Document
from lokalocr.textview import TextLayout, render

__all__ = ["export_txt", "to_txt"]


def to_txt(document: Document, layout: TextLayout = "simplified") -> str:
    text = render(document, layout)
    return text + "\n" if text else ""


def export_txt(
    document: Document,
    path: Path,
    *,
    layout: TextLayout = "simplified",
    overwrite: bool = False,
) -> Path:
    newline = "\r\n" if sys.platform == "win32" else "\n"
    data = to_txt(document, layout).replace("\n", newline)
    return write_atomic(path, data.encode("utf-8"), overwrite=overwrite)
