"""Render the app icon SVG to PNG (256 px) and a multi-size Windows .ico (§7.8)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "src" / "lokalocr" / "ui" / "resources"


def main() -> int:
    from PIL import Image
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    QGuiApplication(["make_icons"])
    renderer = QSvgRenderer(str(RES / "app_icon.svg"))
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    png = RES / "app_icon_256.png"
    image.save(str(png), "PNG")
    Image.open(png).save(
        RES / "app_icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Wrote {png} and app_icon.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
