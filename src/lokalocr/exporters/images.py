"""Write extracted figures to an ``obrazy/`` folder (§5 full mode)."""

from __future__ import annotations

from pathlib import Path

from lokalocr.exporters.common import OutputExistsError, write_atomic
from lokalocr.model import Document

__all__ = ["IMAGES_DIR", "export_images", "image_name"]

IMAGES_DIR = "obrazy"


def image_name(stem: str, ref: str) -> str:
    """File name of a figure: the output stem keeps several documents apart in one folder."""
    return f"{stem}_{ref}" if stem else ref


def export_images(
    document: Document, folder: Path, *, stem: str = "", overwrite: bool = False
) -> list[Path]:
    """Save all figures; refuses to replace a different file unless the caller confirmed it.

    An existing file with identical content (e.g. Markdown and HTML saved for
    the same document) is left as it is.
    """
    targets = [(folder / image_name(stem, ref), data) for ref, data in document.images.items()]
    pending = [(p, d) for p, d in targets if not (p.is_file() and p.read_bytes() == d)]
    if not overwrite and any(p.exists() for p, _ in pending):
        raise OutputExistsError("image file already exists")
    for path, data in pending:
        write_atomic(path, data, overwrite=True)
    return [p for p, _ in targets]
