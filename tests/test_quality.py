"""CER regression guard on a few hard synthetic cases (baseline: docs/quality/cer-baseline.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

import make_fixtures as fx
from lokalocr.engines.tesseract import TesseractEngine
from lokalocr.pipeline import Pipeline, ProcessOptions
from lokalocr.textview import simplified
from measure_cer import cer

CASES = [
    # (document, dpi, variant, max CER) — limits leave headroom over the baseline.
    ("invoice", 200, "rotated", 0.03),
    ("cv", 150, "noisy", 0.04),
    ("cv", 300, "lowcontrast", 0.03),
]


@pytest.mark.tesseract
@pytest.mark.slow
@pytest.mark.parametrize(("name", "dpi", "variant", "limit"), CASES)
def test_cer_within_baseline(
    tmp_path: Path, name: str, dpi: int, variant: str, limit: float
) -> None:
    doc = fx.degrade(fx.DOCUMENTS[name](dpi), variant)
    path = fx.save(doc, tmp_path / f"{name}.png")
    result = Pipeline(TesseractEngine()).process(path, ProcessOptions(pdf_dpi=dpi))
    assert cer(doc.truth, simplified(result)) <= limit
