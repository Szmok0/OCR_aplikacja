"""Installation self-test: ``LokalOCR.exe --selftest report.json`` (stage 7).

Renders a Polish sentence with a system font, runs the real OCR pipeline
offline and writes a JSON report. Used by CI on the packaged build and by
the owner after installing on a new machine. Exit code 0 = OK.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QFont

SAMPLE = "Zażółć gęślą jaźń 2024"


# Windows fonts with Polish diacritics, loaded from file: Qt's offscreen
# platform (used in CI) does not see the system font directory.
_WINDOWS_FONTS = ("arial.ttf", "segoeui.ttf", "tahoma.ttf")


def _sample_font() -> QFont:
    from PySide6.QtGui import QFont, QFontDatabase

    if sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in _WINDOWS_FONTS:
            if not (fonts / name).is_file():
                continue
            font_id = QFontDatabase.addApplicationFont(str(fonts / name))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                return QFont(families[0])
    return QFont()


def _render_sample(path: Path) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    image = QImage(1800, 300, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    font = _sample_font()
    font.setPixelSize(90)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(image.rect(), int(Qt.AlignmentFlag.AlignCenter), SAMPLE)
    painter.end()
    image.setDotsPerMeterX(11811)  # 300 dpi
    image.setDotsPerMeterY(11811)
    image.save(str(path))  # format from the .png suffix


def run(report_path: Path | None) -> int:
    from lokalocr import __version__, netguard
    from lokalocr.engines.docling_engine import find_models_dir, is_available
    from lokalocr.engines.tesseract import TesseractEngine
    from lokalocr.pipeline import Pipeline

    report: dict[str, object] = {"version": __version__, "network_guard": netguard.is_installed()}
    ok = False
    try:
        engine = TesseractEngine()
        report["tesseract"] = engine.version()
        report["languages"] = sorted(engine.available_languages())
        with tempfile.TemporaryDirectory(prefix="lokalocr-selftest-") as tmp:
            sample = Path(tmp) / "sample.png"
            _render_sample(sample)
            started = time.monotonic()
            document = Pipeline(engine).process(sample)
            report["seconds"] = round(time.monotonic() - started, 2)
            text = document.plain_text()
            report["text"] = text
            ok = "gęślą" in text and "2024" in text
        report["full_mode"] = is_available()
        report["models"] = str(find_models_dir() or "")
    except Exception as exc:  # the report must be written whatever happens
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["ok"] = ok
    data = json.dumps(report, ensure_ascii=False, indent=2)
    if report_path is not None:
        report_path.write_text(data, encoding="utf-8")
    else:
        print(data)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
