"""SVG icons (§7.8) coloured from theme tokens at load time."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from lokalocr.ui import theme

RESOURCES = Path(__file__).resolve().parent / "resources"
ICONS_DIR = RESOURCES / "icons"
APP_ICON_SVG = RESOURCES / "app_icon.svg"


def icon_path(name: str) -> Path:
    return ICONS_DIR / f"{name}.svg"


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    svg = icon_path(name).read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    px = max(1, round(size * ratio))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def pixmap(name: str, size: int = 18, color_token: str = "text", ratio: float = 2.0) -> QPixmap:
    return _pixmap(name, getattr(theme.tokens(), color_token), size, ratio)


def icon(name: str, color_token: str = "text", size: int = 18) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, size, color_token), QIcon.Mode.Normal)
    result.addPixmap(pixmap(name, size, "text_muted"), QIcon.Mode.Disabled)
    return result


def _render_svg(path: Path, px: int) -> QImage:
    renderer = QSvgRenderer(str(path))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    return image


def app_pixmap(size: int = 36, ratio: float = 2.0) -> QPixmap:
    pixmap = QPixmap.fromImage(_render_svg(APP_ICON_SVG, round(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def app_icon() -> QIcon:
    result = QIcon()
    for px in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(QPixmap.fromImage(_render_svg(APP_ICON_SVG, px)))
    return result


def clear_cache() -> None:
    """Call after a theme switch so icons pick up the new colours."""
    _pixmap.cache_clear()
