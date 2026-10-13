"""Map a Docling ``DoclingDocument`` onto the neutral :class:`Document` (§3).

Pure functions without model access, so they are testable with documents
built by hand. Coordinates are kept in PDF points (``Page.dpi = 72``) with a
top-left origin, like every other engine's page coordinates.
"""

from __future__ import annotations

import io
from typing import Any

from lokalocr.model import BBox, Block, BlockType, Line, Page, Table, TableCell

__all__ = ["map_pages"]

_HEADING_MAX = 6


def _bbox(item: Any, page_height: float) -> tuple[int, BBox | None]:
    prov = getattr(item, "prov", None) or []
    if not prov:
        return 0, None
    first = prov[0]
    box = first.bbox.to_top_left_origin(page_height=page_height)
    return int(first.page_no), BBox(
        round(box.l), round(box.t), max(1, round(box.r - box.l)), max(1, round(box.b - box.t))
    )


def _png(image: Any) -> bytes | None:
    if image is None:
        return None
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _table(item: Any) -> Table:
    data = item.data
    cells = [
        TableCell(
            row=int(c.start_row_offset_idx),
            col=int(c.start_col_offset_idx),
            text=str(c.text or ""),
            row_span=max(1, int(getattr(c, "row_span", 1) or 1)),
            col_span=max(1, int(getattr(c, "col_span", 1) or 1)),
            header=bool(getattr(c, "column_header", False) or getattr(c, "row_header", False)),
        )
        for c in data.table_cells
    ]
    return Table(rows=int(data.num_rows), cols=int(data.num_cols), cells=cells)


def map_pages(
    doc: Any,
    *,
    page_offset: int = 0,
    confidence: dict[int, float] | None = None,
    images: dict[str, bytes] | None = None,
) -> list[Page]:
    """Convert a DoclingDocument into pages of blocks.

    ``page_offset`` shifts page numbers (documents converted page by page);
    extracted figure images are added to ``images`` under ``figure_N.png``.
    """
    from docling_core.types.doc import (  # local import: optional dependency
        DocItemLabel,
        ListItem,
        PictureItem,
        SectionHeaderItem,
        TableItem,
        TextItem,
        TitleItem,
    )

    images = images if images is not None else {}
    confidence = confidence or {}
    pages: dict[int, Page] = {}
    for page_no, page in sorted(doc.pages.items()):
        number = int(page_no) + page_offset
        pages[int(page_no)] = Page(
            number=number,
            width=max(1, round(page.size.width)),
            height=max(1, round(page.size.height)),
            dpi=72,
        )
    has_title = any(isinstance(item, TitleItem) for item, _ in doc.iterate_items())
    emitted_captions: set[str] = set()

    def caption_blocks(item: Any, page: Page, conf: float | None) -> list[Block]:
        """Captions referenced by a picture or table (pictures' children are not iterated)."""
        out = []
        for ref in getattr(item, "captions", None) or []:
            cap = ref.resolve(doc)
            cref = str(getattr(cap, "self_ref", ""))
            text = " ".join(str(getattr(cap, "text", "") or "").split())
            if not text or cref in emitted_captions:
                continue
            emitted_captions.add(cref)
            _, cbox = _bbox(cap, page.height)
            out.append(Block(BlockType.CAPTION, text, [Line(text, cbox, conf)], cbox, conf))
        return out

    for item, _level in doc.iterate_items():
        prov = getattr(item, "prov", None) or []
        if not prov:
            continue
        page_no = int(prov[0].page_no)
        page = pages.get(page_no)
        if page is None:
            continue
        _, bbox = _bbox(item, page.height)
        conf = confidence.get(page_no)

        if isinstance(item, TableItem):
            page.blocks.append(
                Block(BlockType.TABLE, bbox=bbox, table=_table(item), confidence=conf)
            )
            page.blocks.extend(caption_blocks(item, page, conf))
            continue
        if isinstance(item, PictureItem):
            ref = f"figure_{len(images) + 1}.png"
            data = _png(item.get_image(doc))
            if data is None:
                continue
            images[ref] = data
            page.blocks.append(
                Block(BlockType.FIGURE, text="", bbox=bbox, image_ref=ref, confidence=conf)
            )
            page.blocks.extend(caption_blocks(item, page, conf))
            continue
        if isinstance(item, TextItem):
            if str(getattr(item, "self_ref", "")) in emitted_captions:
                continue
            text = " ".join(str(item.text or "").split())
            if not text:
                continue
            if isinstance(item, TitleItem):
                block = Block(BlockType.HEADING, text, level=1)
            elif isinstance(item, SectionHeaderItem):
                level = int(getattr(item, "level", 1) or 1) + (1 if has_title else 0)
                block = Block(BlockType.HEADING, text, level=min(_HEADING_MAX, level))
            elif isinstance(item, ListItem):
                block = Block(BlockType.LIST_ITEM, text)
            elif item.label == DocItemLabel.CAPTION:
                emitted_captions.add(str(getattr(item, "self_ref", "")))
                block = Block(BlockType.CAPTION, text)
            else:
                block = Block(BlockType.PARAGRAPH, text)
            block.bbox = bbox
            block.confidence = conf
            block.lines = [Line(text, bbox, conf)]
        else:
            continue
        page.blocks.append(block)
    return [pages[k] for k in sorted(pages)]
