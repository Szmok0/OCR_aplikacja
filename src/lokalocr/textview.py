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

from lokalocr.model import Block, BlockType, Document, Line, Page, block_text

__all__ = ["TextLayout", "original_layout", "render", "simplified"]

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


# A line that ends before this fraction of the block width is a real line
# break (address, list, total), not a wrap inside a paragraph.
_WRAP_FRACTION = 0.75


def _is_wrapped(line: Line, block: Block) -> bool:
    if line.bbox is None or block.bbox is None or block.bbox.width <= 0:
        return True
    return line.bbox.right - block.bbox.x >= _WRAP_FRACTION * block.bbox.width


def simplified_block(block: Block) -> str:
    if block.type is BlockType.TABLE:
        return block_text(block)
    if not block.lines:
        return merge_lines(block.text.splitlines())
    if len(block.lines) < 3:
        # Too few lines to tell wraps from breaks: keep short lines apart.
        wrapped = [len(ln.text) > 40 and _is_wrapped(ln, block) for ln in block.lines[:-1]]
    else:
        wrapped = [_is_wrapped(ln, block) for ln in block.lines[:-1]]
    paragraphs: list[list[str]] = [[]]
    for i, line in enumerate(block.lines):
        paragraphs[-1].append(line.text)
        if i < len(wrapped) and not wrapped[i]:
            paragraphs.append([])
    return "\n".join(merge_lines(p) for p in paragraphs if p)


def simplified(document: Document) -> str:
    parts = [t for page in document.pages for b in page.blocks if (t := simplified_block(b))]
    return "\n\n".join(parts)


def render(document: Document, layout: TextLayout) -> str:
    return original_layout(document) if layout == "original" else simplified(document)
