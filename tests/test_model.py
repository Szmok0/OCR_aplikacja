from __future__ import annotations

from lokalocr.model import (
    BBox,
    Block,
    BlockType,
    Document,
    Line,
    Page,
    Table,
    TableCell,
    block_text,
    sections,
)


def _doc(*blocks: Block) -> Document:
    return Document(pages=[Page(1, 100, 100, 300, list(blocks))])


def test_bbox_union() -> None:
    box = BBox.union([BBox(10, 10, 5, 5), BBox(0, 20, 3, 3)])
    assert box == BBox(0, 10, 15, 13)
    assert BBox.union([]) is None


def test_mean_confidence_prefers_lines() -> None:
    doc = _doc(
        Block(BlockType.PARAGRAPH, "a", [Line("a", confidence=0.5), Line("b", confidence=1.0)]),
        Block(BlockType.PARAGRAPH, "c", confidence=0.1),
    )
    assert doc.mean_confidence == 0.75


def test_mean_confidence_none_without_data() -> None:
    assert _doc(Block(BlockType.PARAGRAPH, "x")).mean_confidence is None


def test_plain_text_and_word_count() -> None:
    doc = _doc(Block(BlockType.PARAGRAPH, "Zażółć gęślą"), Block(BlockType.PARAGRAPH, "jaźń"))
    assert doc.plain_text() == "Zażółć gęślą\n\njaźń"
    assert doc.word_count() == 3


def test_table_text_uses_grid() -> None:
    table = Table(2, 2, [TableCell(0, 0, "a"), TableCell(0, 1, "b"), TableCell(1, 1, "d")])
    assert block_text(Block(BlockType.TABLE, table=table)) == "a\tb\n\td"


def test_sections_tree() -> None:
    h1 = Block(BlockType.HEADING, "Tytuł", level=1)
    h2a = Block(BlockType.HEADING, "A", level=2)
    h2b = Block(BlockType.HEADING, "B", level=2)
    h1b = Block(BlockType.HEADING, "Drugi", level=1)
    pre = Block(BlockType.PARAGRAPH, "wstęp")
    p1 = Block(BlockType.PARAGRAPH, "p1")
    p2 = Block(BlockType.LIST_ITEM, "p2")
    roots = sections(_doc(pre, h1, h2a, p1, h2b, p2, h1b))
    assert [s.title for s in roots] == ["", "Tytuł", "Drugi"]
    assert roots[0].blocks == [pre]
    assert [c.title for c in roots[1].children] == ["A", "B"]
    assert roots[1].children[0].blocks == [p1]
    assert roots[1].children[1].blocks == [p2]
