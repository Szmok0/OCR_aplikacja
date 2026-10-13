from __future__ import annotations

from pathlib import Path

import pytest

from lokalocr.exporters.common import OutputExistsError, default_output_name
from lokalocr.exporters.txt import export_txt, to_txt
from lokalocr.model import Block, BlockType, Document, Page


def _doc() -> Document:
    return Document(pages=[Page(1, 10, 10, 300, [Block(BlockType.PARAGRAPH, "Zażółć\ngęślą")])])


def test_default_output_name() -> None:
    assert default_output_name(Path("/x/umowa skan.pdf"), "txt") == "umowa skan_ocr.txt"
    assert default_output_name(Path("cv.jpg"), ".docx") == "cv_ocr.docx"


def test_export_utf8(tmp_path: Path) -> None:
    out = export_txt(_doc(), tmp_path / "a.txt")
    text = out.read_bytes().decode("utf-8")
    assert "Zażółć gęślą" in text
    assert not text.startswith("﻿")


def test_never_overwrites_without_permission(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(OutputExistsError):
        export_txt(_doc(), target)
    assert target.read_text(encoding="utf-8") == "old"
    export_txt(_doc(), target, overwrite=True)
    assert "Zażółć" in target.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]  # no leftover temp file


def test_layouts() -> None:
    assert to_txt(_doc(), "simplified") == "Zażółć gęślą\n"
    assert to_txt(Document()) == ""
