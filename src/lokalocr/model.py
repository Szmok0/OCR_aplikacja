"""Engine-independent document model (CLAUDE.md §3).

Both processing modes produce a :class:`Document`; the UI and every exporter
consume only this model, never engine-specific output.

Coordinates are in pixels of the page image the engine saw (``Page.dpi``).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

Mode = Literal["basic", "full"]


class BlockType(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"


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
class TableCell:
    row: int
    col: int
    text: str
    row_span: int = 1
    col_span: int = 1
    header: bool = False


@dataclass(slots=True)
class Table:
    rows: int
    cols: int
    cells: list[TableCell] = field(default_factory=list)

    def grid(self) -> list[list[str]]:
        """Dense ``rows x cols`` text grid; spanned cells repeat nothing."""
        out = [["" for _ in range(self.cols)] for _ in range(self.rows)]
        for c in self.cells:
            if 0 <= c.row < self.rows and 0 <= c.col < self.cols:
                out[c.row][c.col] = c.text
        return out


@dataclass(slots=True)
class Block:
    type: BlockType
    text: str = ""
    lines: list[Line] = field(default_factory=list)
    bbox: BBox | None = None
    confidence: float | None = None
    level: int | None = None  # heading level, 1-based
    table: Table | None = None
    image_ref: str | None = None  # key into Document.images


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
    mode: Mode = "basic"
    # Extracted figure images (PNG bytes), referenced by Block.image_ref.
    images: dict[str, bytes] = field(default_factory=dict)

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
    if block.type is BlockType.TABLE and block.table is not None:
        return "\n".join("\t".join(row) for row in block.table.grid())
    if block.text:
        return block.text
    return "\n".join(line.text for line in block.lines)


def page_text(page: Page) -> str:
    return "\n\n".join(t for b in page.blocks if (t := block_text(b)))


@dataclass(slots=True)
class Section:
    """A heading and the blocks under it (derived view, not stored)."""

    heading: Block | None
    page_number: int
    blocks: list[Block] = field(default_factory=list)
    children: list[Section] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.heading.text if self.heading else ""


def sections(document: Document) -> list[Section]:
    """Build the section tree used by the structure window (§3).

    A section is a heading plus the following blocks until the next heading of
    the same or higher level. Blocks before the first heading go into a root
    section without a heading.
    """
    roots: list[Section] = []
    stack: list[tuple[int, Section]] = []
    preamble: Section | None = None
    for page, block in document.blocks():
        if block.type is BlockType.HEADING:
            level = block.level or 1
            section = Section(heading=block, page_number=page.number)
            while stack and stack[-1][0] >= level:
                stack.pop()
            (stack[-1][1].children if stack else roots).append(section)
            stack.append((level, section))
        elif stack:
            stack[-1][1].blocks.append(block)
        else:
            if preamble is None:
                preamble = Section(heading=None, page_number=page.number)
                roots.append(preamble)
            preamble.blocks.append(block)
    return roots
