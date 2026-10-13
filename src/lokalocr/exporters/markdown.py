"""Markdown export: headings, lists, tables and figure links in full mode; paragraphs in basic."""

from __future__ import annotations

import re
from pathlib import Path

from lokalocr.exporters.common import write_atomic
from lokalocr.exporters.structure import items
from lokalocr.model import Document

__all__ = ["IMAGES_DIR", "export_markdown", "to_markdown"]

IMAGES_DIR = "obrazy"

_SPECIAL_AT_START = re.compile(r"^(\s*)([#>*+\-]|\d+[.)])(\s)")


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")
    text = text.replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")
    # Text that would read as a heading, quote or list marker at line start.
    return _SPECIAL_AT_START.sub(lambda m: f"{m.group(1)}\\{m.group(2)}{m.group(3)}", text)


def _cell(text: str) -> str:
    return _escape(" ".join(text.split())).replace("|", "\\|")


def to_markdown(document: Document, *, structure: bool = True) -> str:
    parts: list[str] = []
    for item in items(document, structure=structure):
        if item.kind == "heading":
            parts.append(f"{'#' * min(item.level, 6)} {_escape(item.text)}")
        elif item.kind == "list_item":
            parts.append(f"- {_escape(item.text)}")
        elif item.kind == "table" and item.rows:
            cols = max(len(r) for r in item.rows)
            rows = [list(r) + [""] * (cols - len(r)) for r in item.rows]
            lines = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |", "|" + "---|" * cols]
            lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
            parts.append("\n".join(lines))
        elif item.kind == "figure" and item.image_ref:
            parts.append(f"![{_escape(item.text)}]({IMAGES_DIR}/{item.image_ref})")
        elif item.kind == "caption":
            parts.append(f"*{_escape(item.text)}*")
        else:
            lines_ = item.lines or (item.text,)
            # Two trailing spaces = hard line break inside a paragraph.
            parts.append("  \n".join(_escape(ln) for ln in lines_))
    # Consecutive list items form one list.
    text = "\n\n".join(parts)
    text = re.sub(r"(^- .*)\n\n(?=- )", r"\1\n", text, flags=re.MULTILINE)
    return text + "\n" if text else ""


def export_markdown(
    document: Document, path: Path, *, structure: bool = True, overwrite: bool = False
) -> Path:
    data = to_markdown(document, structure=structure).encode("utf-8")
    return write_atomic(path, data, overwrite=overwrite)
