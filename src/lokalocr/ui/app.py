"""GUI entry point: ``lokalocr-gui`` or ``python -m lokalocr.ui``.

The network guard is installed before Qt or any engine is imported (§6.1).
No windows other than the main window appear at start-up (§7.2).
"""

from __future__ import annotations

from lokalocr import netguard

netguard.install()

import sys  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from pathlib import Path  # noqa: E402

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lokalocr import __version__, config, logsetup, tempdir  # noqa: E402
from lokalocr.config import Settings  # noqa: E402
from lokalocr.engines.base import OcrEngine  # noqa: E402
from lokalocr.ui import icons, theme  # noqa: E402
from lokalocr.ui import strings_pl as S  # noqa: E402
from lokalocr.ui.main_window import MainWindow  # noqa: E402


def _engine() -> OcrEngine:
    from lokalocr.engines.tesseract import TesseractEngine

    return TesseractEngine()


def create_app(argv: Sequence[str] | None = None, settings: Settings | None = None) -> QApplication:
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
    s = settings or Settings()
    theme.apply(app, s.theme, s.font_size or None)
    return app


def main(argv: Sequence[str] | None = None) -> int:
    settings = config.load()
    logsetup.configure(settings.log_level)
    tempdir.set_root(Path(settings.temp_dir) if settings.temp_dir else None)
    tempdir.cleanup()  # leftovers from a previous crash
    app = create_app(argv, settings)
    window = MainWindow(_engine, settings=settings, persist_settings=True)
    window.show()
    window.check_engine()
    try:
        return app.exec()
    finally:
        tempdir.cleanup()


if __name__ == "__main__":
    sys.exit(main())
