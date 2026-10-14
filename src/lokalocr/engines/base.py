"""Engine interface (§3). A new OCR engine is a new class implementing it."""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from PIL import Image

from lokalocr.model import Page


@runtime_checkable
class OcrEngine(Protocol):
    """Recognises text on a single page image."""

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
