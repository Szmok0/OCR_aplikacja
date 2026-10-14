from __future__ import annotations

from lokalocr.model import (
    BBox,
    Block,
    BlockType,
    Document,
    Line,
    Page,
    block_text,
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


def test_block_text_falls_back_to_lines() -> None:
    block = Block(BlockType.PARAGRAPH, lines=[Line("Zażółć"), Line("gęślą jaźń")])
    assert block_text(block) == "Zażółć\ngęślą jaźń"
