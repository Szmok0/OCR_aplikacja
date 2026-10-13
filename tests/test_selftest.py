from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

FONTS = Path(__file__).parent / "fixtures" / "fonts"


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


def test_sample_font_loaded_from_windows_fonts_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil
    import sys

    from lokalocr import selftest
    from lokalocr.ui.app import create_app

    create_app(["test"])
    fonts = tmp_path / "Fonts"
    fonts.mkdir()
    shutil.copy(FONTS / "DejaVuSerif.ttf", fonts / "arial.ttf")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    assert selftest._sample_font().family() == "DejaVu Serif"
