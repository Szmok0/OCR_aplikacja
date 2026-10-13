from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from lokalocr import loader
from lokalocr.errors import (
    CorruptFileError,
    PasswordProtectedError,
    TooLargeError,
    UnsupportedFormatError,
)


@pytest.mark.parametrize(
    ("name", "fmt", "pages"),
    [
        ("cv.png", "png", 1),
        ("cv.jpg", "jpeg", 1),
        ("contract.pdf", "pdf", 2),
        ("contract.tif", "tiff", 2),
    ],
)
def test_open_supported_formats(fixtures_dir: Path, name: str, fmt: str, pages: int) -> None:
    with loader.open_document(fixtures_dir / name) as doc:
        assert doc.format == fmt
        assert doc.page_count == pages
        rendered = list(doc.pages(dpi=100))
    assert [p.number for p in rendered] == list(range(1, pages + 1))
    assert all(p.image.mode == "RGB" for p in rendered)


def test_format_detected_by_content_not_extension(fixtures_dir: Path, tmp_path: Path) -> None:
    disguised = tmp_path / "scan.pdf"
    disguised.write_bytes((fixtures_dir / "cv.png").read_bytes())
    assert loader.detect_format(disguised) == "png"


def test_pdf_render_respects_dpi(fixtures_dir: Path) -> None:
    with loader.open_document(fixtures_dir / "contract.pdf") as doc:
        page = doc.render(0, dpi=72)
    # A4 is 595 x 842 pt.
    assert abs(page.image.width - 595) <= 2
    assert page.dpi == 72


def test_image_dpi_from_metadata(fixtures_dir: Path) -> None:
    with loader.open_document(fixtures_dir / "cv.png") as doc:
        assert doc.render(0).dpi == 200


def test_image_without_dpi_uses_default(tmp_path: Path) -> None:
    path = tmp_path / "x.png"
    Image.new("RGB", (50, 50), "white").save(path)
    with loader.open_document(path) as doc:
        assert doc.render(0).dpi == loader.DEFAULT_IMAGE_DPI


def test_transparent_png_gets_white_background(tmp_path: Path) -> None:
    path = tmp_path / "t.png"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(path)
    with loader.open_document(path) as doc:
        assert doc.render(0).image.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("content", [b"hello world", b"GIF89a....", b"PK\x03\x04docx"])
def test_unsupported_format(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "file.bin"
    path.write_bytes(content)
    with pytest.raises(UnsupportedFormatError):
        loader.open_document(path)


def test_empty_file_is_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    with pytest.raises(CorruptFileError):
        loader.open_document(path)


@pytest.mark.parametrize(
    "magic", [b"%PDF-1.7\n garbage", b"\x89PNG\r\n\x1a\n garbage", b"\xff\xd8\xff garbage"]
)
def test_truncated_files_are_corrupt(tmp_path: Path, magic: bytes) -> None:
    path = tmp_path / "broken"
    path.write_bytes(magic)
    with pytest.raises(CorruptFileError):
        doc = loader.open_document(path)
        doc.render(0)


def test_password_protected_pdf(monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path) -> None:
    def locked(*_a: object, **_k: object) -> None:
        raise pdfium.PdfiumError("Incorrect password error", err_code=4)

    monkeypatch.setattr(pdfium, "PdfDocument", locked)
    with pytest.raises(PasswordProtectedError):
        loader.open_document(fixtures_dir / "contract.pdf")


def test_too_large_pdf_page(monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path) -> None:
    monkeypatch.setattr(loader, "MAX_PAGE_PIXELS", 1000)
    with loader.open_document(fixtures_dir / "contract.pdf") as doc, pytest.raises(TooLargeError):
        doc.render(0, dpi=300)


def test_too_large_image(monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path) -> None:
    monkeypatch.setattr(loader, "MAX_PAGE_PIXELS", 1000)
    with pytest.raises(TooLargeError):
        loader.open_document(fixtures_dir / "cv.png")
