from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image

import make_fixtures as fx
from lokalocr.engines import tesseract as tess
from lokalocr.engines.base import OcrEngine
from lokalocr.errors import CancelledError, EngineMissingError, LanguageDataMissingError
from lokalocr.model import BBox, BlockType
from measure_cer import cer

TSV = "\n".join(
    [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "1\t1\t0\t0\t0\t0\t0\t0\t1000\t1000\t-1\t",
        "5\t1\t1\t1\t1\t1\t100\t100\t50\t20\t96.5\tZażółć",
        "5\t1\t1\t1\t1\t2\t160\t100\t50\t20\t90\tgęślą",
        "5\t1\t1\t1\t2\t1\t100\t130\t40\t20\t80\tjaźń",
        "4\t1\t1\t1\t2\t0\t100\t130\t40\t20\t-1\t",
        "5\t1\t2\t1\t1\t1\t500\t100\t60\t22\t70\tNIP",
        "5\t1\t2\t1\t1\t2\t570\t100\t10\t22\t-1\t ",
    ]
)


def test_tsv_grouping_into_blocks_and_lines() -> None:
    blocks = tess._blocks_from_tsv(TSV)
    assert [b.type for b in blocks] == [BlockType.PARAGRAPH, BlockType.PARAGRAPH]
    first, second = blocks
    assert first.text == "Zażółć gęślą\njaźń"
    assert [ln.text for ln in first.lines] == ["Zażółć gęślą", "jaźń"]
    assert first.lines[0].bbox == BBox(100, 100, 110, 20)
    assert first.lines[0].confidence == pytest.approx(0.9325)
    assert first.bbox == BBox(100, 100, 110, 50)
    assert second.text == "NIP"


def test_tsv_empty() -> None:
    assert tess._blocks_from_tsv("") == []


def test_missing_binary_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(tess.TESSERACT_ENV, str(tmp_path / "nope.exe"))
    with pytest.raises(EngineMissingError):
        tess.find_tesseract()


def test_missing_binary_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(tess.TESSERACT_ENV, raising=False)
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(EngineMissingError):
        tess.find_tesseract()


pytestmark_real = pytest.mark.tesseract


@pytest.fixture(scope="module")
def engine() -> tess.TesseractEngine:
    return tess.TesseractEngine()


@pytestmark_real
def test_engine_satisfies_protocol(engine: tess.TesseractEngine) -> None:
    assert isinstance(engine, OcrEngine)
    assert engine.version().startswith("tesseract")
    assert {"pol", "eng"} <= engine.available_languages()


@pytestmark_real
def test_recognize_polish_diacritics(engine: tess.TesseractEngine) -> None:
    page = fx.make_cv(300).pages[0]
    result = engine.recognize(page.image, "pol+eng", dpi=300)
    text = "\n".join(b.text for b in result.blocks)
    assert "Przykładowa" in text and "Źródło" in text
    assert cer("\n".join(page.truth), text) < 0.05
    assert all(b.confidence is not None and 0 < b.confidence <= 1 for b in result.blocks)
    assert (result.width, result.height) == page.image.size


@pytestmark_real
def test_missing_language_data(engine: tess.TesseractEngine) -> None:
    image = Image.new("L", (100, 100), 255)
    with pytest.raises(LanguageDataMissingError):
        engine.recognize(image, "xyz", dpi=300)
    with pytest.raises(LanguageDataMissingError):
        engine.check_languages("pol+xyz")


@pytestmark_real
def test_cancel_kills_process(engine: tess.TesseractEngine) -> None:
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CancelledError):
        engine.recognize(
            fx.make_contract(300, pages=1).pages[0].image, "pol", dpi=300, cancel=cancel
        )


@pytestmark_real
def test_searchable_pdf(engine: tess.TesseractEngine) -> None:
    data = engine.searchable_pdf(Image.new("L", (300, 300), 255), "pol", dpi=300)
    assert data.startswith(b"%PDF-")


@pytestmark_real
def test_cancel_during_recognition(engine: tess.TesseractEngine) -> None:
    import time

    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    image = fx.make_contract(300, pages=1).pages[0].image
    started = time.monotonic()
    timer.start()
    with pytest.raises(CancelledError):
        engine.recognize(image, "pol+eng", dpi=300, cancel=cancel)
    assert time.monotonic() - started < 1.5
