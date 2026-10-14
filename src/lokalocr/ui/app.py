"""GUI entry point: ``lokalocr-gui`` or ``python -m lokalocr.ui``.

The network guard is installed before Qt or any engine is imported (§6.1).
No windows other than the main window appear at start-up (§7.2).
"""

from __future__ import annotations

from lokalocr import netguard

netguard.install()

import gc  # noqa: E402
import sys  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from pathlib import Path  # noqa: E402

from PySide6.QtCore import QObject, Qt, QTimer  # noqa: E402
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


GC_INTERVAL_MS = 500


def _collect_garbage() -> None:
    # Same generational thresholds as Python's automatic collector.
    count0, count1, count2 = gc.get_count()
    threshold0, threshold1, threshold2 = gc.get_threshold()
    if count0 > threshold0:
        gc.collect(2 if count2 > threshold2 else 1 if count1 > threshold1 else 0)


def _collect_garbage_in_gui_thread(app: QObject) -> None:
    """Run Python's cyclic garbage collector only in the GUI thread.

    Automatic collection runs in whichever thread happens to allocate. When it
    frees a Qt object from a worker thread (OCR, preview rendering), Qt crashes
    (access violation on Windows). A timer collects in the GUI thread instead.
    """
    if app.findChild(QTimer, "gcTimer") is not None:
        return
    gc.disable()
    timer = QTimer(app)
    timer.setObjectName("gcTimer")
    timer.setInterval(GC_INTERVAL_MS)
    timer.timeout.connect(_collect_garbage)
    timer.start()


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
    _collect_garbage_in_gui_thread(app)
    s = settings or Settings()
    theme.apply(app, s.theme, s.font_size or None)
    return app


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--selftest"]:
        from lokalocr.selftest import run

        create_app(["lokalocr", "-platform", "offscreen"])
        return run(Path(args[1]) if len(args) > 1 else None)
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
