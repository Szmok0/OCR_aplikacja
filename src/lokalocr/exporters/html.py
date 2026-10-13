"""Standalone HTML export (UTF-8, inline CSS, no external resources)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from lokalocr.exporters.common import write_atomic
from lokalocr.exporters.images import IMAGES_DIR, export_images, image_name
from lokalocr.exporters.structure import items
from lokalocr.model import Document

__all__ = ["export_html", "to_html"]

_CSS = """
body { font-family: system-ui, "Segoe UI", sans-serif; line-height: 1.5; max-width: 50rem;
       margin: 2rem auto; padding: 0 1rem; color: #1F2937; }
table { border-collapse: collapse; margin: 1rem 0; }
td, th { border: 1px solid #C9D1DB; padding: .3rem .6rem; text-align: left; vertical-align: top; }
th { background: #F6F6F6; }
img { max-width: 100%; }
figcaption, .caption { color: #5F6876; font-style: italic; }
"""


def to_html(
    document: Document, *, structure: bool = True, title: str = "LokalOCR", image_stem: str = ""
) -> str:
    body: list[str] = []
    in_list = False
    for item in items(document, structure=structure):
        if item.kind == "list_item":
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"  <li>{escape(item.text)}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if item.kind == "heading":
            level = min(item.level, 6)
            body.append(f"<h{level}>{escape(item.text)}</h{level}>")
        elif item.kind == "table" and item.rows:
            rows = []
            for r, row in enumerate(item.rows):
                tag = "th" if r == 0 else "td"
                cells = "".join(f"<{tag}>{escape(c)}</{tag}>" for c in row)
                rows.append(f"  <tr>{cells}</tr>")
            body.append("<table>\n" + "\n".join(rows) + "\n</table>")
        elif item.kind == "figure" and item.image_ref:
            alt = escape(item.text, quote=True)
            src = escape(f"{IMAGES_DIR}/{image_name(image_stem, item.image_ref)}", quote=True)
            body.append(f'<figure><img src="{src}" alt="{alt}"></figure>')
        elif item.kind == "caption":
            body.append(f'<p class="caption">{escape(item.text)}</p>')
        else:
            lines = item.lines or (item.text,)
            body.append("<p>" + "<br>\n".join(escape(ln) for ln in lines) + "</p>")
    if in_list:
        body.append("</ul>")
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="pl">\n<head>\n<meta charset="utf-8">\n<title>{escape(title)}</title>\n'
        f"<style>{_CSS}</style>\n</head>\n<body>\n" + "\n".join(body) + "\n</body>\n</html>\n"
    )


def export_html(
    document: Document,
    path: Path,
    *,
    structure: bool = True,
    title: str = "LokalOCR",
    overwrite: bool = False,
) -> Path:
    html = to_html(document, structure=structure, title=title, image_stem=path.stem)
    result = write_atomic(path, html.encode("utf-8"), overwrite=overwrite)
    if structure and document.mode == "full" and document.images:
        export_images(document, path.parent / IMAGES_DIR, stem=path.stem, overwrite=overwrite)
    return result
