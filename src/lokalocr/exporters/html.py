"""Standalone HTML export (UTF-8, inline CSS, no external resources).

A Content-Security-Policy forbids the browser to load anything (scripts,
images, fonts, styles from elsewhere) when the file is opened (§6).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from lokalocr.exporters.common import paragraph_lines, write_atomic
from lokalocr.model import Document

__all__ = ["CSP", "export_html", "to_html"]

CSP = "default-src 'none'; style-src 'unsafe-inline'"

_CSS = """
body { font-family: system-ui, "Segoe UI", sans-serif; line-height: 1.5; max-width: 50rem;
       margin: 2rem auto; padding: 0 1rem; color: #1F2937; }
"""


def to_html(document: Document, *, title: str = "LokalOCR") -> str:
    body = [
        "<p>" + "<br>\n".join(escape(ln) for ln in lines) + "</p>"
        for lines in paragraph_lines(document)
    ]
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="pl">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n" + "\n".join(body) + "\n</body>\n</html>\n"
    )


def export_html(
    document: Document, path: Path, *, title: str = "LokalOCR", overwrite: bool = False
) -> Path:
    return write_atomic(path, to_html(document, title=title).encode("utf-8"), overwrite=overwrite)
