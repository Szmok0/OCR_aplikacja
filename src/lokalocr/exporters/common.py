"""Helpers shared by exporters."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from lokalocr.errors import ErrorCode, LokalOcrError
from lokalocr.model import Document
from lokalocr.textview import paragraphs

__all__ = ["OutputExistsError", "default_output_name", "paragraph_lines", "write_atomic"]


class OutputExistsError(LokalOcrError):
    code = ErrorCode.OUTPUT_EXISTS


def default_output_name(source: Path, extension: str) -> str:
    """``<name>_ocr.<ext>`` as required by §7.3 zone 6."""
    return f"{source.stem}_ocr.{extension.lstrip('.')}"


def paragraph_lines(document: Document) -> Iterator[tuple[str, ...]]:
    """The paragraphs of the "Tekst uproszczony" view, each as its non-empty lines.

    DOCX, Markdown and HTML keep these lines apart inside one paragraph (addresses,
    lists and totals keep their breaks).
    """
    for text in paragraphs(document):
        lines = tuple(ln for ln in text.split("\n") if ln.strip())
        if lines:
            yield lines


def write_atomic(path: Path, data: bytes, *, overwrite: bool = False) -> Path:
    """Write via a temporary file in the target folder, then rename.

    Never overwrites an existing file unless ``overwrite`` is set (the caller
    asks the user first).
    """
    if path.exists() and not overwrite:
        raise OutputExistsError("output file already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".lokalocr-", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
