from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from docx import Document as DocxDocument
from PIL import Image

import make_fixtures as fx
from lokalocr.exporters.common import OutputExistsError
from lokalocr.exporters.docx import export_docx, to_docx_bytes
from lokalocr.exporters.html import to_html
from lokalocr.exporters.markdown import to_markdown
from lokalocr.model import BBox, Block, BlockType, Document, Line, Page, Table, TableCell
from measure_cer import cer


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 100, 240)).save(buf, "PNG")
    return buf.getvalue()


def full_document() -> Document:
    table = Table(
        2,
        2,
        [
            TableCell(0, 0, "Nazwa", header=True),
            TableCell(0, 1, "Cena"),
            TableCell(1, 0, "Żółte segregatory"),
            TableCell(1, 1, "35,50 | zł"),
        ],
    )
    blocks = [
        Block(BlockType.HEADING, "Zofia Przykładowa", level=1),
        Block(BlockType.PARAGRAPH, "Księgowa z doświadczeniem *gwiazdka* i [nawias]."),
        Block(BlockType.HEADING, "Doświadczenie", level=2),
        Block(BlockType.LIST_ITEM, "Rozliczenia VAT"),
        Block(BlockType.LIST_ITEM, "Płace <i> & kadry"),
        Block(BlockType.TABLE, table=table),
        Block(BlockType.FIGURE, "Zdjęcie", image_ref="figure_1.png"),
        Block(BlockType.CAPTION, "Rys. 1. Zdjęcie profilowe"),
    ]
    return Document(
        pages=[Page(1, 100, 100, 300, blocks)], mode="full", images={"figure_1.png": _png()}
    )


def basic_document() -> Document:
    lines = [
        Line("Przykładowa Firma Sp. z o.o.", BBox(0, 0, 280, 20)),
        Line("ul. Łąkowa 12, 80-001 Gdańsk", BBox(0, 30, 290, 20)),
    ]
    return Document(
        pages=[
            Page(
                1,
                100,
                100,
                300,
                [
                    Block(
                        BlockType.PARAGRAPH,
                        "\n".join(ln.text for ln in lines),
                        lines,
                        BBox(0, 0, 290, 50),
                    ),
                    Block(BlockType.PARAGRAPH, "Zażółć gęślą jaźń"),
                ],
            )
        ]
    )


def test_docx_structure(tmp_path: Path) -> None:
    path = export_docx(full_document(), tmp_path / "a.docx")
    doc = DocxDocument(str(path))
    styles = [(p.style.name if p.style else "", p.text) for p in doc.paragraphs if p.text]
    assert ("Heading 1", "Zofia Przykładowa") in styles
    assert ("Heading 2", "Doświadczenie") in styles
    assert ("List Bullet", "Rozliczenia VAT") in styles
    assert ("Caption", "Rys. 1. Zdjęcie profilowe") in styles
    assert len(doc.tables) == 1
    assert doc.tables[0].cell(1, 0).text == "Żółte segregatory"
    assert len(doc.inline_shapes) == 1


def test_docx_without_structure_is_plain_paragraphs() -> None:
    doc = DocxDocument(io.BytesIO(to_docx_bytes(full_document(), structure=False)))
    assert not doc.tables and not doc.inline_shapes
    assert {p.style.name if p.style else "" for p in doc.paragraphs} == {"Normal"}
    assert any("Żółte segregatory" in p.text for p in doc.paragraphs)


def test_docx_basic_keeps_address_lines() -> None:
    doc = DocxDocument(io.BytesIO(to_docx_bytes(basic_document())))
    first = doc.paragraphs[0]
    assert first.text == "Przykładowa Firma Sp. z o.o.\nul. Łąkowa 12, 80-001 Gdańsk"
    assert doc.paragraphs[1].text == "Zażółć gęślą jaźń"


def test_docx_never_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "a.docx"
    target.write_bytes(b"old")
    with pytest.raises(OutputExistsError):
        export_docx(basic_document(), target)
    assert target.read_bytes() == b"old"


def test_markdown_structure_and_escaping() -> None:
    md = to_markdown(full_document())
    assert "# Zofia Przykładowa" in md
    assert "## Doświadczenie" in md
    assert "- Rozliczenia VAT\n- Płace <i> & kadry" in md
    assert "\\*gwiazdka\\*" in md and "\\[nawias\\]" in md
    assert "| Nazwa | Cena |" in md and "35,50 \\| zł" in md
    assert "![Zdjęcie](obrazy/figure_1.png)" in md
    assert "obrazy/cv_figure_1.png" in to_markdown(full_document(), image_stem="cv")


def test_markdown_escapes_line_start_markers() -> None:
    doc = Document(pages=[Page(1, 1, 1, 300, [Block(BlockType.PARAGRAPH, "# nie nagłówek")])])
    assert to_markdown(doc).startswith("\\# nie nagłówek")


def test_markdown_basic_line_breaks() -> None:
    assert to_markdown(basic_document()).startswith(
        "Przykładowa Firma Sp. z o.o.  \nul. Łąkowa 12, 80-001 Gdańsk\n\nZażółć"
    )


def test_html_structure_and_escaping() -> None:
    html = to_html(full_document(), title="cv <x>")
    assert '<meta charset="utf-8">' in html and "<title>cv &lt;x&gt;</title>" in html
    assert "<h1>Zofia Przykładowa</h1>" in html
    assert "<ul>\n  <li>Rozliczenia VAT</li>\n  <li>Płace &lt;i&gt; &amp; kadry</li>\n</ul>" in html
    assert "<th>Nazwa</th>" in html and "<td>Żółte segregatory</td>" in html
    assert '<img src="obrazy/figure_1.png" alt="Zdjęcie">' in html
    assert "http" not in html  # no external resources


def test_html_basic_paragraphs() -> None:
    html = to_html(basic_document())
    assert "<p>Przykładowa Firma Sp. z o.o.<br>\nul. Łąkowa 12, 80-001 Gdańsk</p>" in html


@pytest.mark.tesseract
def test_searchable_pdf(tmp_path: Path) -> None:
    from lokalocr.engines.tesseract import TesseractEngine
    from lokalocr.exporters.pdf_text import export_searchable_pdf
    from lokalocr.pipeline import ProcessOptions

    contract = fx.make_contract(150, pages=2)
    source = fx.save(contract, tmp_path / "umowa.pdf")
    events: list[str] = []
    out = export_searchable_pdf(
        source,
        tmp_path / "umowa_ocr.pdf",
        TesseractEngine(),
        ProcessOptions(pdf_dpi=150),
        on_progress=lambda e: events.append(e.stage),
    )
    assert set(events) == {"export"}
    pdf = pdfium.PdfDocument(str(out))
    try:
        assert len(pdf) == 2
        width, height = pdf[0].get_size()
        assert abs(width - 595) < 3 and abs(height - 842) < 3  # A4 kept
        text = "".join(pdf[i].get_textpage().get_text_range() for i in range(2))
        assert cer(contract.truth, text) < 0.05
        assert pdf[1].get_textpage().search("Wykonawca").get_next() is not None
    finally:
        pdf.close()
    # JPEG-embedded pages stay small.
    assert out.stat().st_size < 1_000_000 * 2


def test_markdown_and_html_write_images_folder(tmp_path: Path) -> None:
    from lokalocr.exporters.html import export_html
    from lokalocr.exporters.markdown import export_markdown

    export_markdown(full_document(), tmp_path / "cv_ocr.md")
    export_html(full_document(), tmp_path / "cv_ocr.html")
    assert (tmp_path / "obrazy" / "cv_ocr_figure_1.png").read_bytes().startswith(b"\x89PNG")
    html = (tmp_path / "cv_ocr.html").read_text(encoding="utf-8")
    assert 'src="obrazy/cv_ocr_figure_1.png"' in html


def test_images_never_overwritten_silently(tmp_path: Path) -> None:
    from lokalocr.exporters.images import export_images

    folder = tmp_path / "obrazy"
    export_images(full_document(), folder, stem="a")
    export_images(full_document(), folder, stem="a")  # identical content: fine
    (folder / "a_figure_1.png").write_bytes(b"other image")
    with pytest.raises(OutputExistsError):
        export_images(full_document(), folder, stem="a")
    export_images(full_document(), folder, stem="a", overwrite=True)
    export_images(full_document(), folder, stem="b")
    assert sorted(p.name for p in folder.iterdir()) == ["a_figure_1.png", "b_figure_1.png"]
