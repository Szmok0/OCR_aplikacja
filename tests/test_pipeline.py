from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PIL import Image

from lokalocr import netguard
from lokalocr.errors import CancelledError, EmptyResultError
from lokalocr.model import BBox, Block, BlockType, Line, Page
from lokalocr.pipeline import EtaEstimator, Pipeline, ProcessOptions, ProgressEvent
from lokalocr.preprocess import PreprocessOptions
from measure_cer import cer

FAST = ProcessOptions(pdf_dpi=72, preprocess=PreprocessOptions(enabled=False))


class FakeEngine:
    name = "fake"

    def __init__(self, text: str = "Zażółć gęślą jaźń", cancel_after: int | None = None) -> None:
        self.text = text
        self.calls = 0
        self.cancel_after = cancel_after
        self.cancel_event: threading.Event | None = None

    def recognize(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        page_number: int = 1,
        cancel: threading.Event | None = None,
    ) -> Page:
        self.calls += 1
        if self.cancel_after is not None and self.calls >= self.cancel_after and cancel:
            cancel.set()
        line = Line(self.text, BBox(0, 0, 10, 10), 0.9) if self.text else None
        blocks = [Block(BlockType.PARAGRAPH, self.text, [line])] if line else []
        return Page(page_number, image.width, image.height, dpi, blocks)

    def available_languages(self) -> frozenset[str]:
        return frozenset({"pol", "eng"})

    def version(self) -> str:
        return "fake 1.0"


def test_progress_events(fixtures_dir: Path) -> None:
    events: list[ProgressEvent] = []
    doc = Pipeline(FakeEngine()).process(
        fixtures_dir / "contract.pdf", FAST, on_progress=events.append
    )
    assert doc.page_count == 2
    assert [p.number for p in doc.pages] == [1, 2]
    assert events[0].stage == "loading" and events[0].eta_seconds is None
    assert events[-1].percent == 100.0
    percents = [e.percent for e in events]
    assert percents == sorted(percents)
    stages = [e.stage for e in events if e.page == 1]
    assert stages == ["loading", "preprocessing", "ocr"]
    # ETA appears once the first page has been timed.
    assert any(e.eta_seconds is not None for e in events if e.page == 2)


def test_cancel_between_pages(fixtures_dir: Path) -> None:
    engine = FakeEngine(cancel_after=1)
    with pytest.raises(CancelledError):
        Pipeline(engine).process(fixtures_dir / "contract.pdf", FAST, cancel=threading.Event())
    assert engine.calls == 1


def test_empty_result(fixtures_dir: Path) -> None:
    with pytest.raises(EmptyResultError):
        Pipeline(FakeEngine(text="")).process(fixtures_dir / "cv.png", FAST)


def test_eta_moving_average() -> None:
    eta = EtaEstimator(window=2)
    assert eta.remaining(3) is None
    for seconds in (10.0, 2.0, 4.0):
        eta.add(seconds)
    assert eta.remaining(2) == 6.0


@pytest.mark.tesseract
def test_full_processing_with_network_guard_active(fixtures_dir: Path) -> None:
    """§6 mandatory test: a complete document is processed while offline."""
    import make_fixtures as fx
    from lokalocr.engines.tesseract import TesseractEngine

    assert netguard.is_installed()
    doc = Pipeline(TesseractEngine()).process(
        fixtures_dir / "contract.pdf", ProcessOptions(pdf_dpi=150)
    )
    truth = fx.make_contract(150, pages=2).truth
    assert doc.page_count == 2
    assert cer(truth, doc.plain_text()) < 0.05
