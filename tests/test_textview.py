from __future__ import annotations

from lokalocr.model import BBox, Block, BlockType, Document, Line, Page
from lokalocr.textview import merge_lines, original_layout, simplified


def _line(text: str, x: int, y: int, w: int | None = None) -> Line:
    return Line(text, BBox(x, y, w if w is not None else len(text) * 10, 20), 0.9)


def _block(*lines: Line) -> Block:
    return Block(
        BlockType.PARAGRAPH,
        "\n".join(ln.text for ln in lines),
        list(lines),
        BBox.union([ln.bbox for ln in lines if ln.bbox]),
    )


def _doc(*blocks: Block) -> Document:
    return Document(pages=[Page(1, 1000, 1000, 300, list(blocks))])


def test_original_layout_keeps_columns_on_one_row() -> None:
    doc = _doc(
        _block(_line("Sprzedawca:", 100, 100), _line("Firma", 100, 130)),
        _block(_line("Nabywca:", 500, 100), _line("Klient", 500, 130)),
    )
    lines = original_layout(doc).splitlines()
    assert lines[0].startswith("Sprzedawca:") and lines[0].rstrip().endswith("Nabywca:")
    assert lines[0].index("Nabywca:") == 40  # (500 - 100) / 10 px per char
    assert lines[1].index("Klient") == 40


def test_original_layout_inserts_blank_line_for_gap() -> None:
    doc = _doc(_block(_line("Góra", 100, 100)), _block(_line("Dół", 100, 200)))
    assert original_layout(doc) == "Góra\n\n\nDół"


def test_merge_lines_dehyphenates() -> None:
    assert merge_lines(["rozlicze-", "niami podatkowymi"]) == "rozliczeniami podatkowymi"
    assert merge_lines(["Kraków-", "Warszawa"]) == "Kraków- Warszawa"


def test_simplified_merges_wrapped_paragraph() -> None:
    block = _block(
        _line("Księgowa z ośmioletnim doświadczeniem w obsłudze", 100, 100, 600),
        _line("małych i średnich firm, zajmuję się rozliczeniami", 100, 130, 590),
        _line("i płacami.", 100, 160, 100),
    )
    assert simplified(_doc(block)) == (
        "Księgowa z ośmioletnim doświadczeniem w obsłudze małych i średnich firm, "
        "zajmuję się rozliczeniami i płacami."
    )


def test_simplified_keeps_short_lines_apart() -> None:
    block = _block(
        _line("Razem netto: 3 022,00 zł", 100, 100, 240),
        _line("VAT 23%: 695,06 zł", 100, 130, 180),
        _line("Słownie: trzy tysiące siedemset siedemnaście złotych", 100, 160, 600),
    )
    assert simplified(_doc(block)).splitlines() == [
        "Razem netto: 3 022,00 zł",
        "VAT 23%: 695,06 zł",
        "Słownie: trzy tysiące siedemset siedemnaście złotych",
    ]
