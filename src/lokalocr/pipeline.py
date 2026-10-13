"""Processing pipeline: loader -> preprocess -> engine -> DocumentModel (§3).

Emits :class:`ProgressEvent` objects and honours a cancellation event between
and during pages. Never logs document content or file names (§0.2).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lokalocr.engines.base import OcrEngine, StructureEngine
from lokalocr.errors import CancelledError, EmptyResultError
from lokalocr.loader import open_document
from lokalocr.model import Document, Mode, Page
from lokalocr.preprocess import PreprocessOptions, preprocess

__all__ = [
    "EtaEstimator",
    "Pipeline",
    "ProcessOptions",
    "ProgressCallback",
    "ProgressEvent",
    "Stage",
]

_log = logging.getLogger(__name__)

Stage = Literal["loading", "preprocessing", "ocr", "layout", "export"]

LANGUAGES: tuple[str, ...] = ("pol+eng", "pol", "eng")


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: Stage
    page: int  # 1-based page being worked on, 0 before the first page
    page_count: int
    percent: float  # 0-100 for the whole document
    eta_seconds: float | None  # None until there is data ("Szacowanie...")


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True, slots=True)
class ProcessOptions:
    lang: str = "pol+eng"
    mode: Mode = "basic"
    pdf_dpi: int = 300
    preprocess: PreprocessOptions = field(default_factory=PreprocessOptions)


class EtaEstimator:
    """Remaining time from a moving average of seconds per page."""

    def __init__(self, window: int = 5) -> None:
        self.window = window
        self._durations: list[float] = []

    def add(self, seconds: float) -> None:
        self._durations.append(seconds)
        del self._durations[: -self.window]

    def remaining(self, pages_left: int) -> float | None:
        if not self._durations:
            return None
        return pages_left * sum(self._durations) / len(self._durations)


# Share of per-page work done when a stage starts (rest is OCR).
_STAGE_SHARE: dict[Stage, float] = {"loading": 0.0, "preprocessing": 0.1, "ocr": 0.25}


class Pipeline:
    """Runs a document through loader -> preprocess -> engine.

    Pages are rendered and preprocessed one by one in the calling thread; OCR
    of up to ``workers`` pages runs concurrently (each in its own engine
    process), so multi-page scans use several cores.
    """

    def __init__(self, engine: OcrEngine, workers: int = 1) -> None:
        self.engine = engine
        self.workers = max(1, workers)

    def process(
        self,
        path: Path,
        options: ProcessOptions | None = None,
        *,
        on_progress: ProgressCallback | None = None,
        cancel: threading.Event | None = None,
    ) -> Document:
        opts = options or ProcessOptions()
        notify = on_progress or (lambda _e: None)
        cancel = cancel or threading.Event()

        def check_cancel() -> None:
            if cancel.is_set():
                raise CancelledError("processing cancelled")

        started = time.monotonic()
        document = Document(lang=opts.lang, mode=opts.mode)
        notify(ProgressEvent("loading", 0, 0, 0.0, None))
        with open_document(path) as source:
            total = source.page_count
            _log.info(
                "Processing started: format=%s pages=%d mode=%s workers=%d",
                source.format, total, opts.mode, self.workers,
            )  # fmt: skip
            pages: list[Page | None] = [None] * total
            done = 0

            def remaining() -> float | None:
                if done == 0:
                    return None
                return (time.monotonic() - started) / done * (total - done)

            def emit(stage: Stage, index: int) -> None:
                share = _STAGE_SHARE.get(stage, 0.0) / max(1, self.workers)
                pct = min(99.0, 100.0 * (done + share) / total)
                notify(ProgressEvent(stage, index + 1, total, pct, remaining()))

            with ThreadPoolExecutor(
                max_workers=self.workers, thread_name_prefix="ocr-page"
            ) as pool:
                running: dict[Future[Page], int] = {}

                def collect(block: bool) -> None:
                    nonlocal done
                    if not running:
                        return
                    finished, _ = wait(
                        list(running), timeout=None if block else 0, return_when=FIRST_COMPLETED
                    )
                    for future in finished:
                        index = running.pop(future)
                        pages[index] = future.result()  # re-raises engine errors
                        done += 1

                try:
                    for index in range(total):
                        check_cancel()
                        while len(running) >= self.workers:
                            collect(block=True)
                        emit("loading", index)
                        page_image = source.render(index, opts.pdf_dpi)
                        check_cancel()
                        emit("preprocessing", index)
                        image, dpi = preprocess(page_image.image, page_image.dpi, opts.preprocess)
                        page_image.image.close()
                        check_cancel()
                        emit("ocr", index)
                        future = pool.submit(
                            self.engine.recognize,
                            image,
                            opts.lang,
                            dpi=dpi,
                            page_number=index + 1,
                            cancel=cancel,
                        )
                        running[future] = index
                        collect(block=False)
                    while running:
                        collect(block=True)
                except BaseException:
                    cancel.set()  # stop pages still running in the pool
                    raise

            document.pages = [p for p in pages if p is not None]

        notify(ProgressEvent("ocr", total, total, 100.0, 0.0))
        conf = document.mean_confidence
        _log.info(
            "Processing finished: pages=%d seconds=%.1f words=%d mean_conf=%s",
            total,
            time.monotonic() - started,
            document.word_count(),
            f"{conf:.2f}" if conf is not None else "n/a",
        )
        if not document.plain_text().strip():
            raise EmptyResultError("no text recognised")
        return document


def process_full(
    engine: StructureEngine,
    path: Path,
    options: ProcessOptions,
    *,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> Document:
    """Full mode (§5): structure analysis by a :class:`StructureEngine`."""
    notify = on_progress or (lambda _e: None)
    started = time.monotonic()
    notify(ProgressEvent("loading", 0, 0, 0.0, None))
    first_page_at: list[float] = []

    def progress(done: int, total: int) -> None:
        if done == 0:
            first_page_at.append(time.monotonic())  # models loaded, pages start now
            notify(ProgressEvent("layout", 1, total, 2.0, None))
            return
        begin = first_page_at[0] if first_page_at else started
        per_page = (time.monotonic() - begin) / done
        eta = per_page * (total - done)
        pct = 2.0 + 97.0 * done / max(1, total)
        notify(ProgressEvent("layout", min(done + 1, total), total, min(99.0, pct), eta))

    document = engine.analyze(path, options.lang, cancel=cancel, on_progress=progress)
    document.mode = "full"
    notify(ProgressEvent("layout", document.page_count, document.page_count, 100.0, 0.0))
    _log.info(
        "Full-mode analysis finished: pages=%d seconds=%.1f blocks=%d images=%d",
        document.page_count, time.monotonic() - started,
        sum(len(p.blocks) for p in document.pages), len(document.images),
    )  # fmt: skip
    if not document.plain_text().strip() and not document.images:
        raise EmptyResultError("no content recognised")
    return document
