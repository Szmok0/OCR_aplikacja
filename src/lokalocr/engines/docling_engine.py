"""Full mode: document structure with Docling and local models (§5, §10 stage 6).

Docling runs in a child process (``spawn``): cancelling terminates it at once
and its memory is returned when the document is done. The child installs the
network guard before importing Docling and reads models only from the local
``models/`` folder (``artifacts_path``); OCR inside Docling uses the same
Tesseract binary as basic mode.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import multiprocessing as mp
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lokalocr.errors import (
    CancelledError,
    CorruptFileError,
    ErrorCode,
    FullModeUnavailableError,
    LokalOcrError,
    PasswordProtectedError,
)
from lokalocr.model import Document

__all__ = [
    "MANIFEST",
    "MODELS_ENV",
    "DoclingEngine",
    "find_models_dir",
    "is_available",
]

_log = logging.getLogger(__name__)

MODELS_ENV = "LOKALOCR_MODELS"
# Set only by the self-test (synthetic page): the child then reports the full
# traceback, messages included. Otherwise only exception types and code
# locations leave the child, as messages may contain document data (§0.2).
DIAGNOSTICS_ENV = "LOKALOCR_FULL_DIAGNOSTICS"
MANIFEST = "MANIFEST.json"
_POLL_SECONDS = 0.1
_START_TIMEOUT = 600.0  # loading torch and models on a slow laptop takes a while

ProgressFn = Callable[[int, int], None]  # (page, total)


def _candidate_model_dirs() -> list[Path]:
    dirs = []
    env = os.environ.get(MODELS_ENV)
    if env:
        dirs.append(Path(env))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "models")
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "models")
    dirs.append(Path(__file__).resolve().parents[3] / "models")  # source checkout
    return dirs


def _is_hidden(rel: str) -> bool:
    """Dot-files (git metadata of the model repositories) are not needed to run
    the models and may be dropped when the package is copied (CI artifacts,
    archivers), so they never decide whether the models are complete."""
    return any(part.startswith(".") for part in rel.split("/"))


def find_models_dir() -> Path | None:
    """The Docling artifacts folder, if a complete model set is installed."""
    for base in _candidate_model_dirs():
        folder = base / "docling"
        manifest = folder / MANIFEST
        if not manifest.is_file():
            continue
        try:
            entries = json.loads(manifest.read_text(encoding="utf-8"))["files"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if all(
            (folder / e["path"]).is_file() and (folder / e["path"]).stat().st_size == e["size"]
            for e in entries
            if not _is_hidden(e["path"])
        ):
            return folder
    return None


def is_available() -> bool:
    return importlib.util.find_spec("docling") is not None and find_models_dir() is not None


def _child(
    path: str,
    lang: str,
    artifacts: str,
    tesseract_cmd: str,
    tessdata: str | None,
    threads: int,
    pages: int,
    is_pdf: bool,
    out: Any,
) -> None:
    """Child process entry point: convert, map and send back a Document."""
    from lokalocr import netguard

    netguard.install()
    try:
        os.environ["OMP_THREAD_LIMIT"] = "1"

        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import ConversionStatus, InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
        from docling.document_converter import (
            DocumentConverter,
            ImageFormatOption,
            PdfFormatOption,
        )

        from lokalocr.engines.docling_map import map_pages

        options = PdfPipelineOptions(
            artifacts_path=artifacts,
            do_ocr=True,
            ocr_options=TesseractCliOcrOptions(
                lang=lang.split("+"), tesseract_cmd=tesseract_cmd, path=tessdata
            ),
            do_table_structure=True,
            generate_picture_images=True,
            images_scale=2.0,
            do_picture_classification=False,
            do_code_enrichment=False,
            do_formula_enrichment=False,
            enable_remote_services=False,
            accelerator_options=AcceleratorOptions(num_threads=max(1, threads), device="cpu"),
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
            }
        )
        converter.initialize_pipeline(InputFormat.PDF if is_pdf else InputFormat.IMAGE)
        out.put(("started", pages))

        document = Document(lang=lang, mode="full")
        ranges = [(i, i) for i in range(1, pages + 1)] if is_pdf else [(1, 10**6)]
        for first, last in ranges:
            result = converter.convert(path, raises_on_error=False, page_range=(first, last))
            if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
                out.put(("error", ErrorCode.CORRUPT_FILE.value))
                return
            confidence: dict[int, float] = {}
            for page_no, scores in getattr(result.confidence, "pages", {}).items():
                values = [
                    float(v)
                    for v in (
                        getattr(scores, "ocr_score", None),
                        getattr(scores, "layout_score", None),
                    )
                    if v is not None and v == v  # skip NaN
                ]
                if values:
                    confidence[int(page_no)] = sum(values) / len(values)
            document.pages.extend(
                map_pages(result.document, confidence=confidence, images=document.images)
            )
            out.put(("page", min(last, pages)))
        out.put(("result", document))
    except Exception as exc:  # reported to the parent as an error code + safe details
        name = type(exc).__name__
        code = ErrorCode.PASSWORD_PROTECTED if "Password" in name else ErrorCode.INTERNAL
        out.put(("error", code.value, _describe(exc)))


def _describe(exc: BaseException) -> str:
    """Exception chain as types and code locations (full traceback in diagnostics mode)."""
    import traceback

    if os.environ.get(DIAGNOSTICS_ENV) == "1":
        return "".join(traceback.format_exception(exc))
    parts: list[str] = []
    seen: BaseException | None = exc
    while seen is not None and len(parts) < 5:
        frames = traceback.extract_tb(seen.__traceback__)[-3:]
        where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
        parts.append(f"{type(seen).__name__} at {where or '?'}")
        seen = seen.__cause__ or seen.__context__
    return " | caused by ".join(parts)


class DoclingEngine:
    """:class:`StructureEngine` backed by Docling in a child process."""

    name = "docling"

    def __init__(self, models_dir: Path | None = None, threads: int = 2) -> None:
        self.models_dir = models_dir or find_models_dir()
        self.threads = threads

    def is_available(self) -> bool:
        return importlib.util.find_spec("docling") is not None and self.models_dir is not None

    def analyze(
        self,
        path: Path,
        lang: str,
        *,
        cancel: threading.Event | None = None,
        on_progress: ProgressFn | None = None,
    ) -> Document:
        if not self.is_available() or self.models_dir is None:
            raise FullModeUnavailableError("docling or its models are not installed")
        from lokalocr.engines.tesseract import find_tesseract
        from lokalocr.loader import open_document

        binary, tessdata = find_tesseract()
        with open_document(path) as source:  # validates the file and counts pages
            pages = source.page_count
            is_pdf = source.format == "pdf"

        ctx = mp.get_context("spawn")
        out: Any = ctx.Queue()
        process = ctx.Process(
            target=_child,
            args=(str(path), lang, str(self.models_dir), str(binary),
                  str(tessdata) if tessdata else None, self.threads, pages, is_pdf, out),
            daemon=True,
        )  # fmt: skip
        process.start()
        started = time.monotonic()
        got_start = False
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    raise CancelledError("full-mode analysis cancelled")
                try:
                    message = out.get(timeout=_POLL_SECONDS)
                except queue.Empty:
                    if not process.is_alive():
                        raise LokalOcrError("docling process ended unexpectedly") from None
                    if not got_start and time.monotonic() - started > _START_TIMEOUT:
                        raise LokalOcrError("docling did not start in time") from None
                    continue
                kind = message[0]
                if kind == "started":
                    got_start = True
                    if on_progress:
                        on_progress(0, pages)
                elif kind == "page":
                    if on_progress:
                        on_progress(int(message[1]), pages)
                elif kind == "result":
                    document: Document = message[1]
                    return document
                elif kind == "error":
                    detail = str(message[2]) if len(message) > 2 else ""
                    if detail:
                        _log.error("Full-mode analysis failed: %s", detail)
                    code = ErrorCode(message[1])
                    if code is ErrorCode.PASSWORD_PROTECTED:
                        raise PasswordProtectedError("password protected")
                    if code is ErrorCode.CORRUPT_FILE:
                        raise CorruptFileError("docling could not convert the document")
                    raise LokalOcrError(f"docling failed: {detail}", code=code)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            out.close()
