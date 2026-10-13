"""Zone 4: page preview with zoom, pan, magnifier, rotation and deskew (§7.3, §7.11).

Pages are rendered in a background thread at a fixed preview resolution and
kept in a small in-memory cache (never on disk, §6.5).
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QObject, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QIntValidator,
    QMouseEvent,
    QNativeGestureEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lokalocr.errors import LokalOcrError
from lokalocr.loader import open_document
from lokalocr.logsafe import log_unexpected
from lokalocr.model import BBox, Page
from lokalocr.preprocess import estimate_skew
from lokalocr.ui import icons, theme
from lokalocr.ui import strings_pl as S
from lokalocr.ui.worker import pil_to_qimage

_log = logging.getLogger(__name__)

PREVIEW_DPI = 120
SCREEN_DPI = 96  # "100%" = physical page size at a standard screen density
ZOOM_STEPS = (0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
_CACHE_PAGES = 8


class _Rendered(QObject):
    done = Signal(object, int, object, float)  # path, index, QImage | None, skew


class PageView(QGraphicsView):
    """Graphics view with wheel/pinch zoom and a magnifier tool."""

    zoom_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.zoom = 1.0  # relative to "100%"
        self.rotation = 0.0
        self.magnifier = False
        self.fit_mode = True

    def apply_transform(self) -> None:
        scale = self.zoom * SCREEN_DPI / PREVIEW_DPI
        self.resetTransform()
        self.scale(scale, scale)
        self.rotate(self.rotation)
        self.zoom_changed.emit(self.zoom)

    def set_zoom(self, zoom: float) -> None:
        self.fit_mode = False
        self.zoom = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], zoom))
        self.apply_transform()

    def zoom_in(self) -> None:
        self.set_zoom(next((z for z in ZOOM_STEPS if z > self.zoom + 1e-6), ZOOM_STEPS[-1]))

    def zoom_out(self) -> None:
        self.set_zoom(
            next((z for z in reversed(ZOOM_STEPS) if z < self.zoom - 1e-6), ZOOM_STEPS[0])
        )

    def fit(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        self.fit_mode = True
        self.resetTransform()
        self.rotate(self.rotation)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        t = self.transform()
        self.zoom = (t.m11() ** 2 + t.m12() ** 2) ** 0.5 / (SCREEN_DPI / PREVIEW_DPI)
        self.zoom_changed.emit(self.zoom)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self.fit_mode:
            self.fit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            (self.zoom_in if event.angleDelta().y() > 0 else self.zoom_out)()
            event.accept()
        else:
            super().wheelEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if isinstance(event, QNativeGestureEvent) and (
            event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture
        ):
            self.set_zoom(self.zoom * (1.0 + event.value()))
            return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.magnifier and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
        ):
            zoom_out = event.button() == Qt.MouseButton.RightButton or bool(
                event.modifiers() & Qt.KeyboardModifier.AltModifier
            )
            (self.zoom_out if zoom_out else self.zoom_in)()
            self.centerOn(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        super().mousePressEvent(event)


class PagePreview(QFrame):
    """Toolbar + page view. Call :meth:`show_document` with a file and its pages."""

    page_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PreviewPanel")
        self._path: Path | None = None
        self._pages: list[Page] = []
        self._page_count = 0
        self._index = 0
        self._cache: OrderedDict[tuple[Path, int], tuple[QImage, float]] = OrderedDict()
        self._pending: Future[None] | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")
        self._signals = _Rendered()
        self._signals.done.connect(self._on_rendered)
        self._overlay_visible = False
        self._highlight: BBox | None = None
        self._skew = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = PageView()

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(2)
        self.prev_btn = self._tool("icon_prev", S.PREV_PAGE, self.prev_page)
        self.next_btn = self._tool("icon_next", S.NEXT_PAGE, self.next_page)
        self.page_spin = QLineEdit("1")
        self.page_spin.setObjectName("PageSpin")
        self.page_spin.setFixedWidth(48)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_spin.setAccessibleName(S.PAGE_NUMBER)
        self._page_validator = QIntValidator(1, 1, self.page_spin)
        self.page_spin.setValidator(self._page_validator)
        self.page_spin.editingFinished.connect(self._on_page_entered)
        self.page_total = QLabel("/ 0")
        self.zoom_out_btn = self._tool("icon_zoom_out", S.ZOOM_OUT, lambda: self.view.zoom_out())
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(44)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_in_btn = self._tool("icon_zoom_in", S.ZOOM_IN, lambda: self.view.zoom_in())
        self.fit_btn = self._tool("icon_fit", S.FIT, lambda: self.view.fit())
        self.hand_btn = self._tool("icon_hand", S.HAND_TOOL, None, checkable=True)
        self.magnifier_btn = self._tool("icon_magnifier", S.MAGNIFIER_TOOL, None, checkable=True)
        tools = QButtonGroup(self)
        tools.setExclusive(False)
        tools.addButton(self.hand_btn)
        tools.addButton(self.magnifier_btn)
        self.hand_btn.toggled.connect(self._set_hand)
        self.magnifier_btn.toggled.connect(self._set_magnifier)
        self.rotate_left_btn = self._tool(
            "icon_rotate_left", S.ROTATE_LEFT, lambda: self.rotate(-90)
        )
        self.rotate_right_btn = self._tool(
            "icon_rotate_right", S.ROTATE_RIGHT, lambda: self.rotate(90)
        )
        self.deskew_btn = self._tool("icon_deskew", S.DESKEW, self.deskew)
        widget: QWidget
        for widget in (self.prev_btn, self.next_btn):
            bar.addWidget(widget)
        bar.addSpacing(4)
        bar.addWidget(self.page_spin)
        bar.addWidget(self.page_total)
        bar.addStretch()
        for widget in (self.zoom_out_btn, self.zoom_label, self.zoom_in_btn):
            bar.addWidget(widget)
        bar.addSpacing(8)
        for widget in (
            self.fit_btn,
            self.hand_btn,
            self.magnifier_btn,
            self.rotate_left_btn,
            self.rotate_right_btn,
            self.deskew_btn,
        ):
            bar.addWidget(widget)
        self.toolbar = QWidget()
        self.toolbar.setLayout(bar)
        layout.addWidget(self.toolbar)

        self.view.zoom_changed.connect(lambda z: self.zoom_label.setText(f"{round(z * 100)}%"))
        layout.addWidget(self.view, 1)

        self.placeholder = QLabel(S.WORKSPACE_EMPTY_HINT)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setProperty("muted", True)
        layout.addWidget(self.placeholder, 1)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._overlay_items: list[QGraphicsRectItem] = []
        self.refresh_theme()
        self.clear()

    def _tool(self, icon_name: str, tip: str, slot: object, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setProperty("iconName", icon_name)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setCheckable(checkable)
        button.setAutoRaise(True)
        if slot is not None:
            button.clicked.connect(slot)
        return button

    def refresh_theme(self) -> None:
        for button in self.toolbar.findChildren(QToolButton):
            name = button.property("iconName")
            if name:
                button.setIcon(icons.icon(str(name)))
        self.view.setBackgroundBrush(QBrush(theme.color("preview_bg")))
        self._draw_overlay()

    # --- tools ---------------------------------------------------------------

    def _set_hand(self, on: bool) -> None:
        if on:
            self.magnifier_btn.setChecked(False)
        self.view.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag if on else QGraphicsView.DragMode.NoDrag
        )

    def _set_magnifier(self, on: bool) -> None:
        if on:
            self.hand_btn.setChecked(False)
        self.view.magnifier = on
        self.view.viewport().setCursor(
            Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor
        )

    def rotate(self, degrees: float) -> None:
        self.view.rotation = (self.view.rotation + degrees) % 360
        if self.view.fit_mode:
            self.view.fit()
        else:
            self.view.apply_transform()

    def deskew(self) -> None:
        """Straighten the preview by the detected skew of the current page."""
        if abs(self._skew) < 0.05:
            return
        self.rotate(self._skew)
        self._skew = 0.0

    # --- content ---------------------------------------------------------------------

    def clear(self) -> None:
        self._path = None
        self._pages = []
        self._page_count = 0
        self._index = 0
        self.view.scene().clear()
        self._pixmap_item = None
        self._overlay_items = []
        self.view.hide()
        self.placeholder.show()
        self.toolbar.setEnabled(False)
        self.page_total.setText("/ 0")

    def show_document(
        self, path: Path, page_count: int | None, pages: list[Page] | None = None, index: int = 0
    ) -> None:
        same = path == self._path
        self._path = path
        self._page_count = max(1, page_count or 1)
        self._pages = pages or []
        self._page_validator.setTop(self._page_count)
        self.page_total.setText(f"/ {self._page_count}")
        self.toolbar.setEnabled(True)
        self.view.show()
        self.placeholder.hide()
        if not same:
            self.view.rotation = 0.0
            self.view.fit_mode = True
        self.go_to(index if not same else self._index)

    def set_pages(self, pages: list[Page]) -> None:
        self._pages = pages
        self._draw_overlay()

    @property
    def index(self) -> int:
        return self._index

    def go_to(self, index: int) -> None:
        if self._path is None:
            return
        self._index = max(0, min(self._page_count - 1, index))
        self.page_spin.setText(str(self._index + 1))
        self.prev_btn.setEnabled(self._index > 0)
        self.next_btn.setEnabled(self._index < self._page_count - 1)
        key = (self._path, self._index)
        if key in self._cache:
            self._cache.move_to_end(key)
            image, skew = self._cache[key]
            self._show_image(image, skew)
        else:
            self._request(self._path, self._index)
        self.page_changed.emit(self._index)

    def _on_page_entered(self) -> None:
        text = self.page_spin.text()
        if text.isdigit():
            self.go_to(int(text) - 1)

    def next_page(self) -> None:
        self.go_to(self._index + 1)

    def prev_page(self) -> None:
        self.go_to(self._index - 1)

    def _request(self, path: Path, index: int) -> None:
        signals = self._signals

        def render() -> None:
            try:
                with open_document(path) as doc:
                    page = doc.render(index, PREVIEW_DPI)
                gray = np.asarray(page.image.convert("L"))
                skew = estimate_skew(gray)
                signals.done.emit(path, index, pil_to_qimage(page.image), skew)
            except LokalOcrError:
                signals.done.emit(path, index, None, 0.0)
            except Exception as exc:
                log_unexpected(_log, exc, "preview")
                signals.done.emit(path, index, None, 0.0)

        self._pending = self._pool.submit(render)

    def _on_rendered(self, path: Path, index: int, image: QImage | None, skew: float) -> None:
        if image is not None:
            self._cache[(path, index)] = (image, skew)
            while len(self._cache) > _CACHE_PAGES:
                self._cache.popitem(last=False)
        if path != self._path or index != self._index:
            return
        if image is None:
            self.view.hide()
            self.placeholder.setText(S.PREVIEW_FAILED)
            self.placeholder.show()
            return
        self._show_image(image, skew)

    def _show_image(self, image: QImage, skew: float) -> None:
        self._skew = skew
        self.deskew_btn.setEnabled(abs(skew) >= 0.05)
        scene = self.view.scene()
        scene.clear()
        self._overlay_items = []
        self._pixmap_item = scene.addPixmap(QPixmap.fromImage(image))
        scene.setSceneRect(QRectF(image.rect()).adjusted(-40, -40, 40, 40))
        self.view.show()
        self.placeholder.hide()
        if self.view.fit_mode:
            self.view.fit()
        else:
            self.view.apply_transform()
        self._draw_overlay()

    # --- block overlay (Podgląd tab, structure window) ------------------------------------

    def set_overlay_visible(self, visible: bool) -> None:
        self._overlay_visible = visible
        self._draw_overlay()

    def highlight(self, bbox: BBox | None) -> None:
        self._highlight = bbox
        self._draw_overlay()

    def _draw_overlay(self) -> None:
        scene = self.view.scene()
        for item in self._overlay_items:
            scene.removeItem(item)
        self._overlay_items = []
        if self._pixmap_item is None or self._index >= len(self._pages):
            return
        page = self._pages[self._index]
        if page.dpi <= 0:
            return
        # Block boxes are in the coordinates of the image the engine saw.
        sx = self._pixmap_item.pixmap().width() / max(1, page.width)
        sy = self._pixmap_item.pixmap().height() / max(1, page.height)
        accent = theme.color("accent")
        boxes: list[tuple[BBox, bool]] = []
        if self._overlay_visible:
            boxes += [(b.bbox, False) for b in page.blocks if b.bbox is not None]
        if self._highlight is not None:
            boxes.append((self._highlight, True))
        for bbox, strong in boxes:
            rect = QGraphicsRectItem(bbox.x * sx, bbox.y * sy, bbox.width * sx, bbox.height * sy)
            pen = QPen(accent, 2.5 if strong else 1.2)
            pen.setCosmetic(True)
            rect.setPen(pen)
            fill = QColor(accent)
            fill.setAlpha(60 if strong else 22)
            rect.setBrush(fill)
            scene.addItem(rect)
            self._overlay_items.append(rect)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._cache.clear()
