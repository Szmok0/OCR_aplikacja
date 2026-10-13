"""Shared logic for structured exporters (DOCX, Markdown, HTML).

Exporters walk a flat list of :class:`Item` built here, so all of them agree
on what "keep structure" means (§5): with ``structure=False`` every block is
exported as plain paragraphs, even in full mode.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from lokalocr.model import BlockType, Document
from lokalocr.textview import paragraphs, simplified_block

ItemKind = Literal["heading", "paragraph", "list_item", "table", "figure", "caption"]


@dataclass(frozen=True, slots=True)
class Item:
    kind: ItemKind
    text: str = ""
    lines: tuple[str, ...] = ()  # paragraph lines that must stay separate
    level: int = 1
    rows: tuple[tuple[str, ...], ...] = ()
    image_ref: str | None = None


def _paragraph_item(text: str) -> Item:
    lines = tuple(ln for ln in text.split("\n") if ln.strip())
    return Item("paragraph", text=" ".join(lines), lines=lines)


def items(document: Document, *, structure: bool) -> Iterator[Item]:
    if not structure or document.mode == "basic":
        # Plain text: the same paragraphs as the "Tekst uproszczony" view.
        for text in paragraphs(document):
            item = _paragraph_item(text)
            if item.text:
                yield item
        return

    for _page, block in document.blocks():
        if block.type is BlockType.HEADING:
            yield Item("heading", text=" ".join(block.text.split()), level=max(1, block.level or 1))
        elif block.type is BlockType.LIST_ITEM:
            yield Item("list_item", text=" ".join(simplified_block(block).split()))
        elif block.type is BlockType.TABLE and block.table is not None:
            yield Item("table", rows=tuple(tuple(row) for row in block.table.grid()))
        elif block.type is BlockType.FIGURE:
            if block.image_ref and block.image_ref in document.images:
                yield Item("figure", text=block.text, image_ref=block.image_ref)
        elif block.type is BlockType.CAPTION:
            yield Item("caption", text=" ".join(block.text.split()))
        else:
            item = _paragraph_item(simplified_block(block))
            if item.text:
                yield item
