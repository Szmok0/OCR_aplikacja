"""Docling -> DocumentModel mapping, with a hand-built DoclingDocument (no models)."""

from __future__ import annotations

import pytest

pytest.importorskip("docling_core")

from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ImageRef,
    ProvenanceItem,
    Size,
    TableData,
)
from docling_core.types.doc import (
    TableCell as DlCell,
)
from PIL import Image

from lokalocr.engines.docling_map import map_pages
from lokalocr.model import BlockType


def _prov(page: int, l: float, t: float, r: float, b: float) -> ProvenanceItem:  # noqa: E741
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.BOTTOMLEFT),
        charspan=(0, 0),
    )


def build() -> DoclingDocument:
    doc = DoclingDocument(name="synthetic")
    doc.add_page(page_no=1, size=Size(width=595, height=842))
    doc.add_page(page_no=2, size=Size(width=595, height=842))
    doc.add_title(text="Zofia Przykładowa", prov=_prov(1, 50, 800, 300, 780))
    doc.add_heading(text="Doświadczenie", level=1, prov=_prov(1, 50, 760, 200, 745))
    doc.add_text(
        label=DocItemLabel.TEXT,
        text="Księgowa  z\ndoświadczeniem.",
        prov=_prov(1, 50, 740, 500, 700),
    )
    group = doc.add_list_group()
    doc.add_list_item(text="Rozliczenia VAT", parent=group, prov=_prov(1, 60, 690, 300, 680))
    doc.add_list_item(text="Płace", parent=group, prov=_prov(1, 60, 678, 300, 668))
    cells = [
        DlCell(
            text="Nazwa",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            column_header=True,
        ),
        DlCell(
            text="Cena",
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
            column_header=True,
        ),
        DlCell(
            text="Żółte segregatory",
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=0,
            end_col_offset_idx=2,
            col_span=2,
        ),
    ]
    doc.add_table(
        data=TableData(num_rows=2, num_cols=2, table_cells=cells), prov=_prov(2, 50, 800, 500, 700)
    )
    image = Image.new("RGB", (80, 60), (20, 120, 240))
    # As in Docling's output: the caption is a child of the picture and referenced by it.
    picture = doc.add_picture(
        image=ImageRef.from_pil(image, dpi=72), prov=_prov(2, 50, 600, 130, 540)
    )
    caption = doc.add_text(
        label=DocItemLabel.CAPTION,
        text="Rys. 1. Logo",
        parent=picture,
        prov=_prov(2, 50, 535, 200, 525),
    )
    picture.captions.append(caption.get_ref())
    return doc


def test_mapping_types_levels_and_pages() -> None:
    images: dict[str, bytes] = {}
    pages = map_pages(build(), confidence={1: 0.9, 2: 0.8}, images=images)
    assert [p.number for p in pages] == [1, 2]
    assert (pages[0].width, pages[0].height, pages[0].dpi) == (595, 842, 72)
    kinds = [(b.type, b.level) for b in pages[0].blocks]
    assert kinds == [
        (BlockType.HEADING, 1),
        (BlockType.HEADING, 2),  # section header under a title
        (BlockType.PARAGRAPH, None),
        (BlockType.LIST_ITEM, None),
        (BlockType.LIST_ITEM, None),
    ]
    assert pages[0].blocks[2].text == "Księgowa z doświadczeniem."  # whitespace merged
    assert all(b.confidence == 0.9 for b in pages[0].blocks)


def test_bbox_is_top_left_in_points() -> None:
    heading = map_pages(build())[0].blocks[0]
    assert heading.bbox is not None
    assert (heading.bbox.x, heading.bbox.y, heading.bbox.width, heading.bbox.height) == (
        50,
        42,
        250,
        20,
    )


def test_table_and_figure() -> None:
    images: dict[str, bytes] = {}
    page2 = map_pages(build(), images=images)[1]
    table = page2.blocks[0]
    assert table.type is BlockType.TABLE and table.table is not None
    assert table.table.grid() == [["Nazwa", "Cena"], ["Żółte segregatory", ""]]
    assert table.table.cells[2].col_span == 2
    assert table.table.cells[0].header
    figure = page2.blocks[1]
    assert figure.type is BlockType.FIGURE and figure.image_ref == "figure_1.png"
    assert images["figure_1.png"].startswith(b"\x89PNG")
    assert page2.blocks[2].type is BlockType.CAPTION
    assert page2.blocks[2].text == "Rys. 1. Logo"


def test_caption_not_duplicated() -> None:
    page2 = map_pages(build())[1]
    captions = [b for b in page2.blocks if b.type is BlockType.CAPTION]
    assert [c.text for c in captions] == ["Rys. 1. Logo"]
