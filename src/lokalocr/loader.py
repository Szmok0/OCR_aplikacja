"""Input loading: PDF, PNG, JPEG and (multi-page) TIFF as page images (§3).

The format is detected from file content, not the extension. Pages are
rendered lazily so a large PDF never sits in memory as a whole.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal, Self

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from lokalocr.errors import (
    CorruptFileError,
    PasswordProtectedError,
    TooLargeError,
    UnsupportedFormatError,
)

__all__ = [
    "DEFAULT_IMAGE_DPI",
    "MAX_PAGE_PIXELS",
    "SUPPORTED_EXTENSIONS",
    "InputFormat",
    "OpenedDocument",
    "PageImage",
    "detect_format",
    "open_document",
]

_log = logging.getLogger(__name__)

InputFormat = Literal["pdf", "png", "jpeg", "tiff"]

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"})

# Used when an image carries no usable resolution (typical for photos).
DEFAULT_IMAGE_DPI = 300
_PLAUSIBLE_DPI = range(100, 1201)

# Upper bound for a single rendered page (~ A3 at 600 dpi is 70 MP).
MAX_PAGE_PIXELS = 120_000_000

_MAGIC: list[tuple[bytes, InputFormat]] = [
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"II+\x00", "tiff"),  # BigTIFF
    (b"MM\x00+", "tiff"),
]


@dataclass(slots=True)
class PageImage:
    number: int  # 1-based
    image: Image.Image  # RGB
    dpi: int


def detect_format(path: Path) -> InputFormat:
    try:
        with path.open("rb") as fh:
            head = fh.read(1024)
    except OSError as exc:
        raise CorruptFileError("cannot read input file") from exc
    if not head:
        raise CorruptFileError("empty file")
    for magic, fmt in _MAGIC:
        if head.startswith(magic):
            return fmt
    # Some PDF writers put junk before the header; the spec allows 1 KiB.
    if b"%PDF-" in head:
        return "pdf"
    raise UnsupportedFormatError("unrecognised file signature")


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        # 16-bit greyscale scans: scale to 8 bit.
        return image.point(lambda v: v / 256).convert("L").convert("RGB")
    return image.convert("RGB")


def _image_dpi(image: Image.Image) -> int:
    dpi = image.info.get("dpi")
    if isinstance(dpi, tuple) and dpi:
        try:
            value = round(float(dpi[0]))
        except (TypeError, ValueError):
            value = 0
        if value in _PLAUSIBLE_DPI:
            return value
    return DEFAULT_IMAGE_DPI


class OpenedDocument:
    """An open input file. Use as a context manager."""

    def __init__(self, path: Path, fmt: InputFormat) -> None:
        self.format: InputFormat = fmt
        self._pdf: pdfium.PdfDocument | None = None
        self._image: Image.Image | None = None
        if fmt == "pdf":
            self._pdf = _open_pdf(path)
            self.page_count = len(self._pdf)
        else:
            self._image = _open_image(path)
            self.page_count = getattr(self._image, "n_frames", 1)
        if self.page_count < 1:
            self.close()
            raise CorruptFileError("document has no pages")

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None
        if self._image is not None:
            self._image.close()
            self._image = None

    def render(self, index: int, dpi: int = 300) -> PageImage:
        """Render page ``index`` (0-based). ``dpi`` applies to PDF pages only."""
        if not 0 <= index < self.page_count:
            raise IndexError(index)
        if self._pdf is not None:
            return _render_pdf_page(self._pdf, index, dpi)
        assert self._image is not None
        return _render_image_frame(self._image, index)

    def pages(self, dpi: int = 300) -> Iterator[PageImage]:
        for i in range(self.page_count):
            yield self.render(i, dpi)


def open_document(path: Path) -> OpenedDocument:
    return OpenedDocument(path, detect_format(path))


def _open_pdf(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        if exc.err_code in (pdfium_raw.FPDF_ERR_PASSWORD, pdfium_raw.FPDF_ERR_SECURITY):
            raise PasswordProtectedError("PDF is password protected") from exc
        raise CorruptFileError(f"PDF could not be opened (pdfium code {exc.err_code})") from exc
    except OSError as exc:
        raise CorruptFileError("PDF could not be read") from exc


def _render_pdf_page(pdf: pdfium.PdfDocument, index: int, dpi: int) -> PageImage:
    try:
        page = pdf[index]
    except pdfium.PdfiumError as exc:
        raise CorruptFileError(f"PDF page {index + 1} is damaged") from exc
    try:
        width_pt, height_pt = page.get_size()
        scale = dpi / 72
        if width_pt * scale * height_pt * scale > MAX_PAGE_PIXELS:
            raise TooLargeError(f"page {index + 1} too large at {dpi} dpi")
        try:
            bitmap = page.render(scale=scale, may_draw_forms=True)
        except pdfium.PdfiumError as exc:
            raise CorruptFileError(f"PDF page {index + 1} could not be rendered") from exc
        except MemoryError as exc:
            raise TooLargeError(f"out of memory rendering page {index + 1}") from exc
        image = _to_rgb(bitmap.to_pil())
        bitmap.close()
    finally:
        page.close()
    return PageImage(number=index + 1, image=image, dpi=dpi)


def _open_image(path: Path) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(path)
            if image.width * image.height > MAX_PAGE_PIXELS:
                image.close()
                raise TooLargeError("image too large")
            return image
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise TooLargeError("image too large") from exc
    except UnidentifiedImageError as exc:
        raise CorruptFileError("image could not be decoded") from exc
    except OSError as exc:
        raise CorruptFileError("image could not be read") from exc


def _render_image_frame(image: Image.Image, index: int) -> PageImage:
    try:
        frame = ImageSequence.Iterator(image)[index]
        if frame.width * frame.height > MAX_PAGE_PIXELS:
            raise TooLargeError(f"frame {index + 1} too large")
        frame.load()
        dpi = _image_dpi(frame)
        rgb = _to_rgb(ImageOps.exif_transpose(frame) or frame)
        # Detach from the file so the next frame seek does not mutate it.
        rgb = rgb.copy()
    except (OSError, SyntaxError, ValueError) as exc:
        raise CorruptFileError(f"image frame {index + 1} could not be decoded") from exc
    except MemoryError as exc:
        raise TooLargeError(f"out of memory decoding frame {index + 1}") from exc
    return PageImage(number=index + 1, image=rgb, dpi=dpi)
