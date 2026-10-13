"""DOCX export with python-docx (§5): a clean, editable document, not a page replica."""

from __future__ import annotations

import io
from pathlib import Path

from docx import Document as DocxDocument
from docx.enum.text import WD_BREAK
from docx.shared import Inches, Pt

from lokalocr.exporters.common import write_atomic
from lokalocr.exporters.structure import items
from lokalocr.model import Document

__all__ = ["export_docx", "to_docx_bytes"]

_MAX_IMAGE_WIDTH = Inches(6.0)


def to_docx_bytes(document: Document, *, structure: bool = True) -> bytes:
    out = DocxDocument()
    normal = out.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for item in items(document, structure=structure):
        if item.kind == "heading":
            out.add_heading(item.text, level=min(item.level, 9))
        elif item.kind == "list_item":
            out.add_paragraph(item.text, style="List Bullet")
        elif item.kind == "table":
            if not item.rows:
                continue
            cols = max(len(r) for r in item.rows)
            table = out.add_table(rows=len(item.rows), cols=cols)
            table.style = "Table Grid"
            for r, row in enumerate(item.rows):
                for c, text in enumerate(row):
                    table.cell(r, c).text = text
            out.add_paragraph()
        elif item.kind == "figure" and item.image_ref:
            data = document.images[item.image_ref]
            out.add_picture(io.BytesIO(data), width=_MAX_IMAGE_WIDTH)
        elif item.kind == "caption":
            out.add_paragraph(item.text, style="Caption")
        else:
            paragraph = out.add_paragraph()
            lines = item.lines or (item.text,)
            for i, line in enumerate(lines):
                run = paragraph.add_run(line)
                if i < len(lines) - 1:
                    run.add_break(WD_BREAK.LINE)
    buf = io.BytesIO()
    out.save(buf)
    return buf.getvalue()


def export_docx(
    document: Document, path: Path, *, structure: bool = True, overwrite: bool = False
) -> Path:
    return write_atomic(path, to_docx_bytes(document, structure=structure), overwrite=overwrite)
