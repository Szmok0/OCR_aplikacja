"""Installation self-test: ``LokalOCR.exe --selftest report.json [--full]`` (stage 7).

Renders a Polish sentence with a system font, runs the real OCR pipeline
offline and writes a JSON report. With ``--full`` it also runs full mode
(Docling, in its child process) on a synthetic CV page with a photo and
checks that the photo is extracted. Used by CI on the packaged build and by
the owner after installing on a new machine. Exit code 0 = OK. The report
holds only synthetic sample text, never user documents.
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


def _render_cv_page(path: Path) -> None:
    """A synthetic CV page: a photo-like picture, a name heading and text (150 dpi)."""
    import numpy as np
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    width, height = 1240, 1754
    page = QImage(width, height, QImage.Format.Format_RGB32)
    page.fill(QColor("white"))
    # Photo: smooth colour gradients with noise, like a scanned portrait.
    rng = np.random.default_rng(7)
    ph, pw = 360, 290
    y, x = np.mgrid[0:ph, 0:pw]
    base = np.stack(
        [150 + 70 * np.sin(x / 40), 120 + 60 * np.cos(y / 35), 140 + 50 * np.sin((x + y) / 60)],
        axis=-1,
    )
    photo = np.clip(base + rng.normal(0, 18, base.shape), 0, 255).astype(np.uint8)
    photo_img = QImage(photo.tobytes(), pw, ph, pw * 3, QImage.Format.Format_RGB888).copy()
    painter = QPainter(page)
    painter.drawImage(110, 110, photo_img)
    painter.setPen(QColor("black"))
    font = _sample_font()
    font.setPixelSize(54)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRect(460, 150, 700, 80), int(Qt.AlignmentFlag.AlignLeft), "Anna Przykładowa")
    font.setPixelSize(28)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(
        QRect(460, 240, 700, 40), int(Qt.AlignmentFlag.AlignLeft), "Specjalistka ds. księgowości"
    )
    font.setPixelSize(36)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        QRect(110, 560, 1000, 60), int(Qt.AlignmentFlag.AlignLeft), "DOŚWIADCZENIE ZAWODOWE"
    )
    font.setPixelSize(26)
    font.setBold(False)
    painter.setFont(font)
    lines = [
        "Główna księgowa, Biuro Rachunkowe Przykład Sp. z o.o. (2019 – obecnie)",
        "Prowadzenie pełnej księgowości oraz rozliczeń podatkowych klientów.",
        "Przygotowanie deklaracji VAT, CIT i PIT; nadzór nad zespołem.",
        "Samodzielna księgowa, Hurtownia Źródło S.A. (2016 – 2019)",
    ]
    for i, line in enumerate(lines):
        painter.drawText(QRect(110, 650 + i * 50, 1050, 44), int(Qt.AlignmentFlag.AlignLeft), line)
    painter.end()
    page.setDotsPerMeterX(5906)  # 150 dpi
    page.setDotsPerMeterY(5906)
    page.save(str(path))


def _run_full(report: dict[str, object], tmp: Path) -> bool:
    from lokalocr.engines.docling_engine import DoclingEngine
    from lokalocr.model import BlockType
    from lokalocr.pipeline import ProcessOptions, process_full

    sample = tmp / "cv.png"
    _render_cv_page(sample)
    started = time.monotonic()
    document = process_full(DoclingEngine(threads=2), sample, ProcessOptions(mode="full"))
    types = [block.type for _, block in document.blocks()]
    report["full_seconds"] = round(time.monotonic() - started, 1)
    report["full_blocks"] = {t.value: types.count(t) for t in sorted(set(types), key=str)}
    report["full_images"] = len(document.images)
    return BlockType.FIGURE in types and len(document.images) >= 1


def run(report_path: Path | None, full: bool = False) -> int:
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
        if full:
            if not is_available():
                ok = False
                report["full_error"] = "full mode is not available"
            else:
                with tempfile.TemporaryDirectory(prefix="lokalocr-selftest-") as tmp:
                    report["full_ok"] = _run_full(report, Path(tmp))
                ok = ok and bool(report["full_ok"])
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
    args = [a for a in sys.argv[1:] if a != "--full"]
    sys.exit(run(Path(args[0]) if args else None, full="--full" in sys.argv[1:]))
