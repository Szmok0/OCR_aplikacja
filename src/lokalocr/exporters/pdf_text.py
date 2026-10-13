"""Searchable PDF: page images with an invisible text layer (§5, scenario 3).

Each page is rendered, preprocessed like for OCR, and sent to Tesseract's PDF
renderer (as JPEG, which Tesseract embeds as-is, keeping files small). The
single-page PDFs are merged in memory with pypdfium2, so nothing but the
final file touches the disk. OCR runs again during export; progress is
reported as the "export" stage.
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import pypdfium2 as pdfium
from PIL import Image

from lokalocr.errors import CancelledError
from lokalocr.exporters.common import write_atomic
from lokalocr.loader import _PDFIUM_LOCK, open_document
from lokalocr.pipeline import EtaEstimator, ProcessOptions, ProgressCallback, ProgressEvent
from lokalocr.preprocess import preprocess

__all__ = ["PdfRenderer", "export_searchable_pdf"]

JPEG_QUALITY = 80


@runtime_checkable
class PdfRenderer(Protocol):
    def searchable_pdf(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        cancel: threading.Event | None = None,
        jpeg_quality: int | None = 80,
    ) -> bytes: ...


def export_searchable_pdf(
    source: Path,
    path: Path,
    engine: PdfRenderer,
    options: ProcessOptions,
    *,
    overwrite: bool = False,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    notify = on_progress or (lambda _e: None)
    eta = EtaEstimator()
    pages: list[bytes] = []
    with open_document(source) as doc:
        total = doc.page_count
        for index in range(total):
            if cancel is not None and cancel.is_set():
                raise CancelledError("export cancelled")
            started = time.monotonic()
            notify(
                ProgressEvent(
                    "export", index + 1, total, 100.0 * index / total, eta.remaining(total - index)
                )
            )
            page = doc.render(index, options.pdf_dpi)
            image, dpi = preprocess(page.image, page.dpi, options.preprocess)
            pages.append(
                engine.searchable_pdf(
                    image, options.lang, dpi=dpi, cancel=cancel, jpeg_quality=JPEG_QUALITY
                )
            )
            eta.add(time.monotonic() - started)

    with _PDFIUM_LOCK:
        merged = pdfium.PdfDocument.new()
        try:
            for data in pages:
                single = pdfium.PdfDocument(data)
                try:
                    merged.import_pages(single)
                finally:
                    single.close()
            buf = io.BytesIO()
            merged.save(buf)
        finally:
            merged.close()
    notify(ProgressEvent("export", total, total, 100.0, 0.0))
    return write_atomic(path, buf.getvalue(), overwrite=overwrite)
