"""GUI entry point: ``lokalocr-gui`` or ``python -m lokalocr.ui``.

The network guard is installed before Qt or any engine is imported (§6.1).
No windows other than the main window appear at start-up (§7.2).
"""

from __future__ import annotations

from lokalocr import netguard

netguard.install()

import logging  # noqa: E402
import sys  # noqa: E402
from collections.abc import Sequence  # noqa: E402

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lokalocr import __version__, tempdir  # noqa: E402
from lokalocr.engines.base import OcrEngine  # noqa: E402
from lokalocr.ui import icons, theme  # noqa: E402
from lokalocr.ui import strings_pl as S  # noqa: E402
from lokalocr.ui.main_window import MainWindow  # noqa: E402


def _engine() -> OcrEngine:
    from lokalocr.engines.tesseract import TesseractEngine

    return TesseractEngine()


def create_app(argv: Sequence[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName(S.APP_NAME)
    app.setApplicationDisplayName(S.APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LokalOCR")
    app.setWindowIcon(icons.app_icon())
    theme.apply(app, "system")
    return app


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    tempdir.cleanup()  # leftovers from a previous crash
    app = create_app(argv)
    window = MainWindow(_engine)
    window.show()
    try:
        return app.exec()
    finally:
        tempdir.cleanup()


if __name__ == "__main__":
    sys.exit(main())
