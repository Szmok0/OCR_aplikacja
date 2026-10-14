"""Markdown export: the recognised paragraphs, with Markdown syntax escaped."""

from __future__ import annotations

import re
from pathlib import Path

from lokalocr.exporters.common import paragraph_lines, write_atomic
from lokalocr.model import Document

__all__ = ["export_markdown", "to_markdown"]

_SPECIAL_AT_START = re.compile(r"^(\s*)([#>*+\-]|\d+[.)])(\s)")


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")
    text = text.replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")
    # Text that would read as a heading, quote or list marker at line start.
    return _SPECIAL_AT_START.sub(lambda m: f"{m.group(1)}\\{m.group(2)}{m.group(3)}", text)


def to_markdown(document: Document) -> str:
    # Two trailing spaces = hard line break inside a paragraph.
    parts = ["  \n".join(_escape(ln) for ln in lines) for lines in paragraph_lines(document)]
    text = "\n\n".join(parts)
    return text + "\n" if text else ""


def export_markdown(document: Document, path: Path, *, overwrite: bool = False) -> Path:
    return write_atomic(path, to_markdown(document).encode("utf-8"), overwrite=overwrite)
