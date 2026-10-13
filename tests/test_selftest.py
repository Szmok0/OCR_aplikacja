from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")


@pytest.mark.tesseract
def test_selftest_report(tmp_path: Path) -> None:
    from lokalocr import selftest
    from lokalocr.ui.app import create_app

    create_app(["test"])
    report_path = tmp_path / "report.json"
    assert selftest.run(report_path) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["network_guard"] is True
    assert {"pol", "eng"} <= set(report["languages"])
    assert "gęślą" in report["text"]
