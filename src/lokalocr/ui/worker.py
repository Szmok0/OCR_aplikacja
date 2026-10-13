"""Background work for the UI (§7.2): the UI thread never runs OCR or rendering.

Python threads emit Qt signals on a QObject that lives in the GUI thread, so
slots always run there (queued connections).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from lokalocr.engines.base import OcrEngine, StructureEngine
from lokalocr.errors import ErrorCode, LokalOcrError
from lokalocr.loader import probe
from lokalocr.logsafe import log_unexpected
from lokalocr.pipeline import Pipeline, ProcessOptions, ProgressEvent, process_full

__all__ = ["WRITE_FAILED", "ExportController", "ProcessingController", "pil_to_qimage"]

# Error marker for an export that failed at the file-system level.
WRITE_FAILED = "write_failed"

_log = logging.getLogger(__name__)


def pil_to_qimage(image: Image.Image) -> QImage:
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return qimage.copy()  # detach from the Python buffer


class ProcessingController(QObject):
    """Runs one document at a time and probes new files (page count, thumbnail)."""

    progress = Signal(int, object)  # item id, ProgressEvent
    finished = Signal(int, object, object)  # item id, Document, ProcessOptions
    failed = Signal(int, str)  # item id, ErrorCode value
    probed = Signal(int, object, object)  # item id, page count | None, QImage | None
    probe_failed = Signal(int, str)

    def __init__(
        self,
        engine_factory: Callable[[], OcrEngine],
        structure_factory: Callable[[int], StructureEngine] | None = None,
    ) -> None:
        super().__init__()
        self._structure_factory = structure_factory
        self._engine_factory = engine_factory
        self.engine_factory = engine_factory
        self._engine: OcrEngine | None = None
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._current: int | None = None
        self._running = False
        self._probe_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="probe")

    @property
    def busy(self) -> bool:
        return self._running

    @property
    def current_item(self) -> int | None:
        return self._current if self._running else None

    def probe(self, item_id: int, path: Path, thumb_px: int = 96) -> None:
        def run() -> None:
            try:
                pages, thumb = probe(path, thumb_px)
                self.probed.emit(item_id, pages, pil_to_qimage(thumb))
            except LokalOcrError as exc:
                self.probe_failed.emit(item_id, exc.code.value)
            except Exception as exc:
                log_unexpected(_log, exc, "probe")
                self.probe_failed.emit(item_id, ErrorCode.CORRUPT_FILE.value)

        self._probe_pool.submit(run)

    def start(self, item_id: int, path: Path, options: ProcessOptions, workers: int = 1) -> None:
        if self.busy:
            raise RuntimeError("already processing")
        cancel = threading.Event()
        self._cancel = cancel
        self._current = item_id

        def run() -> None:
            outcome: tuple[str, object]
            try:
                emit = lambda e: self.progress.emit(item_id, e)  # noqa: E731
                if options.mode == "full" and self._structure_factory is not None:
                    structure = self._structure_factory(workers)
                    document = process_full(
                        structure, path, options, on_progress=emit, cancel=cancel
                    )
                else:
                    if self._engine is None:
                        self._engine = self._engine_factory()
                    pipeline = Pipeline(self._engine, workers=workers)
                    document = pipeline.process(path, options, on_progress=emit, cancel=cancel)
                outcome = ("ok", document)
            except LokalOcrError as exc:
                outcome = ("error", exc.code.value)
            except MemoryError:
                outcome = ("error", ErrorCode.TOO_LARGE.value)
            except Exception as exc:
                log_unexpected(_log, exc, "processing")
                outcome = ("error", ErrorCode.INTERNAL.value)
            # Clear "busy" before notifying, so the next item can start at once.
            self._running = False
            if outcome[0] == "ok":
                self.finished.emit(item_id, outcome[1], options)
            else:
                self.failed.emit(item_id, outcome[1])

        self._running = True
        self._thread = threading.Thread(target=run, name="ocr-worker", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def shutdown(self, timeout: float = 5.0) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.join(timeout)
        self._probe_pool.shutdown(wait=False, cancel_futures=True)


class ExportController(QObject):
    """Runs one export job at a time in the background (PDF export repeats OCR)."""

    progress = Signal(int, object)  # item id, ProgressEvent
    finished = Signal(int, object)  # item id, output Path
    failed = Signal(int, str)  # item id, ErrorCode value

    def __init__(self) -> None:
        super().__init__()
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._current: int | None = None

    @property
    def busy(self) -> bool:
        return self._running

    @property
    def current_item(self) -> int | None:
        return self._current if self._running else None

    def start(
        self,
        item_id: int,
        job: Callable[[Callable[[ProgressEvent], None], threading.Event], Path],
    ) -> None:
        if self._running:
            raise RuntimeError("already exporting")
        cancel = threading.Event()
        self._cancel = cancel
        self._current = item_id

        def run() -> None:
            outcome: tuple[str, object]
            try:
                path = job(lambda e: self.progress.emit(item_id, e), cancel)
                outcome = ("ok", path)
            except LokalOcrError as exc:
                outcome = ("error", exc.code.value)
            except OSError:
                outcome = ("error", WRITE_FAILED)
            except Exception as exc:
                log_unexpected(_log, exc, "export")
                outcome = ("error", ErrorCode.INTERNAL.value)
            self._running = False
            if outcome[0] == "ok":
                self.finished.emit(item_id, outcome[1])
            else:
                self.failed.emit(item_id, outcome[1])

        self._running = True
        self._thread = threading.Thread(target=run, name="export-worker", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def shutdown(self, timeout: float = 5.0) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.join(timeout)
