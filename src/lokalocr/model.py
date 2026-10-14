"""Engine-independent document model (CLAUDE.md §3).

The OCR engine produces a :class:`Document`; the UI and every exporter consume
only this model, never engine-specific output.

Coordinates are in pixels of the page image the engine saw (``Page.dpi``).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum


class BlockType(StrEnum):
    # Tesseract recognises text paragraphs only; other engines may add types.
    PARAGRAPH = "paragraph"


@dataclass(frozen=True, slots=True)
class BBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @staticmethod
    def union(boxes: list[BBox]) -> BBox | None:
        if not boxes:
            return None
        x = min(b.x for b in boxes)
        y = min(b.y for b in boxes)
        return BBox(x, y, max(b.right for b in boxes) - x, max(b.bottom for b in boxes) - y)


@dataclass(slots=True)
class Line:
    text: str
    bbox: BBox | None = None
    confidence: float | None = None


@dataclass(slots=True)
class Block:
    type: BlockType
    text: str = ""
    lines: list[Line] = field(default_factory=list)
    bbox: BBox | None = None
    confidence: float | None = None


@dataclass(slots=True)
class Page:
    number: int  # 1-based
    width: int
    height: int
    dpi: int
    blocks: list[Block] = field(default_factory=list)


@dataclass(slots=True)
class Document:
    pages: list[Page] = field(default_factory=list)
    lang: str = "pol+eng"

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def blocks(self) -> Iterator[tuple[Page, Block]]:
        for page in self.pages:
            for block in page.blocks:
                yield page, block

    @property
    def mean_confidence(self) -> float | None:
        """Mean line confidence over the whole document, or ``None``."""
        values = [
            line.confidence
            for _, block in self.blocks()
            for line in block.lines
            if line.confidence is not None
        ]
        if not values:
            values = [b.confidence for _, b in self.blocks() if b.confidence is not None]
        return sum(values) / len(values) if values else None

    def plain_text(self) -> str:
        return "\n\n".join(page_text(p) for p in self.pages).strip()

    def word_count(self) -> int:
        return len(self.plain_text().split())


def block_text(block: Block) -> str:
    if block.text:
        return block.text
    return "\n".join(line.text for line in block.lines)


def page_text(page: Page) -> str:
    return "\n\n".join(t for b in page.blocks if (t := block_text(b)))
