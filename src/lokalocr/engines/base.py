"""Engine interfaces (§3). A new engine is a new class implementing one of these."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image

from lokalocr.model import Document, Page


@runtime_checkable
class OcrEngine(Protocol):
    """Recognises text on a single page image (basic mode)."""

    name: str

    def recognize(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        page_number: int = 1,
        cancel: threading.Event | None = None,
    ) -> Page: ...

    def available_languages(self) -> frozenset[str]: ...

    def version(self) -> str: ...


@runtime_checkable
class StructureEngine(Protocol):
    """Analyses a whole document including layout, tables and figures (full mode)."""

    name: str

    def analyze(
        self, path: Path, lang: str, *, cancel: threading.Event | None = None
    ) -> Document: ...

    def is_available(self) -> bool: ...
