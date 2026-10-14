"""Full mode end to end with real Docling and local models (stage 6 acceptance).

Needs ``pip install -e .[full]`` and ``python scripts/fetch_models.py``; CI runs
it in the ``full-mode`` job. Skipped elsewhere.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("docling")

import make_fixtures as fx
from lokalocr import netguard
from lokalocr.engines.docling_engine import DoclingEngine, find_models_dir
from lokalocr.errors import CancelledError
from lokalocr.exporters.docx import to_docx_bytes
from lokalocr.model import BlockType
from lokalocr.pipeline import ProcessOptions, process_full

MODELS = find_models_dir()
if MODELS is None and os.environ.get("LOKALOCR_REQUIRE_MODELS") == "1":
    raise RuntimeError("LOKALOCR_REQUIRE_MODELS=1 but models/docling is missing or incomplete")

pytestmark = [
    pytest.mark.models,
    pytest.mark.docling,
    pytest.mark.tesseract,
    pytest.mark.skipif(MODELS is None, reason="full-mode models not installed"),
]


@pytest.fixture(scope="module")
def engine() -> DoclingEngine:
    return DoclingEngine(threads=2)


def test_invoice_table_is_recognised(engine: DoclingEngine, tmp_path: Path) -> None:
    assert netguard.is_installed()
    path = fx.save(fx.make_invoice(200), tmp_path / "faktura.png")
    doc = process_full(engine, path, ProcessOptions(lang="pol+eng", mode="full"))
    tables = [b for _, b in doc.blocks() if b.type is BlockType.TABLE and b.table]
    assert tables, "no table detected"
    grid = tables[0].table.grid() if tables[0].table else []
    assert len(grid) >= 4
    flat = " ".join(" ".join(row) for row in grid)
    assert "Szkolenie" in flat and "780,00" in flat


def test_cv_structure_to_docx(engine: DoclingEngine, tmp_path: Path) -> None:
    import io

    from docx import Document as DocxDocument

    path = fx.save(fx.make_cv(200), tmp_path / "cv.png")
    doc = process_full(engine, path, ProcessOptions(lang="pol+eng", mode="full"))
    types = [b.type for _, b in doc.blocks()]
    assert types.count(BlockType.HEADING) >= 3
    assert BlockType.LIST_ITEM in types
    docx = DocxDocument(io.BytesIO(to_docx_bytes(doc)))
    styles = {p.style.name for p in docx.paragraphs if p.style is not None}
    assert any(s.startswith("Heading") for s in styles)
    assert "List Bullet" in styles


def test_multipage_progress_and_cancel(engine: DoclingEngine, tmp_path: Path) -> None:
    path = fx.save(fx.make_contract(150, pages=2), tmp_path / "umowa.pdf")
    seen: list[tuple[int, int]] = []
    doc = engine.analyze(path, "pol+eng", on_progress=lambda d, t: seen.append((d, t)))
    assert [p.number for p in doc.pages] == [1, 2]
    assert seen[0] == (0, 2) and seen[-1] == (2, 2)

    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    with pytest.raises(CancelledError):
        engine.analyze(path, "pol+eng", cancel=cancel)


def test_selftest_full_extracts_the_photo(tmp_path: Path) -> None:
    import json

    from lokalocr import selftest
    from lokalocr.ui.app import create_app

    create_app(["test"])
    report_path = tmp_path / "report.json"
    assert selftest.run(report_path, full=True) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["full_ok"] is True and report["full_images"] >= 1
