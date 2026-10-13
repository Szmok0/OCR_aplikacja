"""Processing pipeline: loader -> preprocess -> engine -> DocumentModel (§3).

Emits :class:`ProgressEvent` objects and honours a cancellation event between
and during pages. Never logs document content or file names (§0.2).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lokalocr.engines.base import OcrEngine
from lokalocr.errors import CancelledError, EmptyResultError
from lokalocr.loader import open_document
from lokalocr.model import Document, Mode
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
    def __init__(self, engine: OcrEngine) -> None:
        self.engine = engine

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

        def check_cancel() -> None:
            if cancel is not None and cancel.is_set():
                raise CancelledError("processing cancelled")

        started = time.monotonic()
        eta = EtaEstimator()
        document = Document(lang=opts.lang, mode=opts.mode)
        notify(ProgressEvent("loading", 0, 0, 0.0, None))
        with open_document(path) as source:
            total = source.page_count
            _log.info(
                "Processing started: format=%s pages=%d mode=%s", source.format, total, opts.mode
            )

            def emit(stage: Stage, index: int) -> None:
                pct = 100.0 * (index + _STAGE_SHARE.get(stage, 0.0)) / total
                notify(ProgressEvent(stage, index + 1, total, pct, eta.remaining(total - index)))

            for index in range(total):
                check_cancel()
                page_started = time.monotonic()
                page_no = index + 1
                emit("loading", index)
                page_image = source.render(index, opts.pdf_dpi)
                check_cancel()
                emit("preprocessing", index)
                image, dpi = preprocess(page_image.image, page_image.dpi, opts.preprocess)
                page_image.image.close()
                check_cancel()
                emit("ocr", index)
                page = self.engine.recognize(
                    image, opts.lang, dpi=dpi, page_number=page_no, cancel=cancel
                )
                document.pages.append(page)
                eta.add(time.monotonic() - page_started)

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
