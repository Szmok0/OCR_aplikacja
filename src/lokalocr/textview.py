"""Text renderings of a :class:`Document` for the result panel and TXT export (§7.3, zone 5).

* "Oryginalny układ" keeps line breaks and approximates horizontal position
  with spaces (meant for a monospace font).
* "Tekst uproszczony" merges each block's lines into a single paragraph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Literal

from lokalocr.model import Block, Document, Line, Page, block_text

__all__ = ["TextLayout", "original_layout", "paragraphs", "render", "simplified"]

TextLayout = Literal["original", "simplified"]

_HYPHEN_BREAK = re.compile(r"(?<=\w)-$")


@dataclass(slots=True)
class _Row:
    top: int
    bottom: int
    lines: list[Line]

    @property
    def center(self) -> float:
        return (self.top + self.bottom) / 2


def _positioned_lines(page: Page) -> list[Line]:
    return [ln for b in page.blocks for ln in b.lines if ln.bbox is not None and ln.text]


def original_layout_page(page: Page) -> str:
    lines = _positioned_lines(page)
    if not lines:
        return "\n\n".join(block_text(b) for b in page.blocks if block_text(b))
    char_w = median(
        [ln.bbox.width / len(ln.text) for ln in lines if ln.bbox and len(ln.text) >= 3] or [10.0]
    )
    line_h = median([ln.bbox.height for ln in lines if ln.bbox]) or 1
    left = min(ln.bbox.x for ln in lines if ln.bbox)

    rows: list[_Row] = []
    for ln in sorted(lines, key=lambda x: x.bbox.y if x.bbox else 0):
        assert ln.bbox is not None
        center = ln.bbox.y + ln.bbox.height / 2
        if rows and abs(center - rows[-1].center) < line_h * 0.5:
            row = rows[-1]
            row.lines.append(ln)
            row.top = min(row.top, ln.bbox.y)
            row.bottom = max(row.bottom, ln.bbox.bottom)
        else:
            rows.append(_Row(ln.bbox.y, ln.bbox.bottom, [ln]))

    out: list[str] = []
    prev_bottom: int | None = None
    for row in rows:
        if prev_bottom is not None:
            gap = row.top - prev_bottom
            blanks = min(2, int(gap / (line_h * 1.2)))
            out.extend([""] * blanks)
        text = ""
        for ln in sorted(row.lines, key=lambda x: x.bbox.x if x.bbox else 0):
            assert ln.bbox is not None
            col = round((ln.bbox.x - left) / char_w)
            if text:
                col = max(col, len(text) + 1)
            text = text.ljust(col) + ln.text
        out.append(text.rstrip())
        prev_bottom = row.bottom
    return "\n".join(out)


def original_layout(document: Document) -> str:
    return "\n\n".join(original_layout_page(p) for p in document.pages).strip("\n")


def merge_lines(lines: list[str]) -> str:
    merged = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if merged and _HYPHEN_BREAK.search(merged) and line[:1].islower():
            merged = merged[:-1] + line
        else:
            merged = f"{merged} {line}" if merged else line
    return merged


# Lines shorter than this are treated as deliberate (addresses, totals, list
# items); prose on a page is wider than this at any normal font size.
MIN_PROSE_LINE = 40


def _is_wrapped(line: Line, next_line: Line, block: Block) -> bool:
    """True if ``line`` ended only because ``next_line``'s first word did not fit.

    That is how text reflow decides line breaks, so it separates wrapped
    paragraphs from real breaks (addresses, lists, totals) better than a
    fixed width threshold.
    """
    words = next_line.text.split()
    if line.bbox is None or block.bbox is None or not line.text or not words:
        return True
    if len(line.text) < MIN_PROSE_LINE:
        return False
    char_w = line.bbox.width / max(1, len(line.text))
    needed = (len(words[0]) + 1) * char_w
    return line.bbox.right + needed > block.bbox.right


def simplified_block(block: Block) -> str:
    if not block.lines:
        return merge_lines(block.text.splitlines())
    lines = block.lines
    paragraphs: list[list[str]] = [[]]
    for i, line in enumerate(lines):
        paragraphs[-1].append(line.text)
        if i + 1 < len(lines) and not _is_wrapped(line, lines[i + 1], block):
            paragraphs.append([])
    return "\n".join(merge_lines(p) for p in paragraphs if p)


def _continues(prev: Block, block: Block) -> bool:
    """Tesseract sometimes splits one paragraph into two blocks; detect that."""
    if not prev.lines or not block.lines:
        return False
    return block.lines[0].text[:1].islower() and _is_wrapped(prev.lines[-1], block.lines[0], prev)


def paragraphs(document: Document) -> list[str]:
    """Simplified paragraphs in reading order, re-joining paragraphs split across blocks."""
    out: list[str] = []
    for page in document.pages:
        prev: Block | None = None
        for block in page.blocks:
            text = simplified_block(block)
            if not text:
                continue
            if out and prev is not None and _continues(prev, block):
                last = out[-1]
                out[-1] = merge_lines([last, text]) if last.endswith("-") else f"{last} {text}"
            else:
                out.append(text)
            prev = block
    return out


def simplified(document: Document) -> str:
    return "\n\n".join(paragraphs(document))


def render(document: Document, layout: TextLayout) -> str:
    return original_layout(document) if layout == "original" else simplified(document)
