"""Zone 4: page preview with zoom, pan, magnifier, rotation, deskew and area selection (§7.3).

Pages are rendered in a background thread at a fixed preview resolution and
kept in a small in-memory cache (never on disk, §6.5).
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QImage,
    QIntValidator,
    QKeyEvent,
    QMouseEvent,
    QNativeGestureEvent,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
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
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lokalocr.errors import LokalOcrError
from lokalocr.loader import open_document
from lokalocr.logsafe import log_unexpected
from lokalocr.model import Page
from lokalocr.preprocess import estimate_skew
from lokalocr.ui import icons, theme
from lokalocr.ui import strings_pl as S
from lokalocr.ui.worker import pil_to_qimage

_log = logging.getLogger(__name__)

PREVIEW_DPI = 120
SCREEN_DPI = 96  # "100%" = physical page size at a standard screen density
ZOOM_STEPS = (0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
_CACHE_PAGES = 8
CROP_DPI = 300  # selections are cut from a fresh render, not from the preview
_MIN_SELECTION = 8  # scene pixels (~1.7 mm at the preview resolution)


class _Rendered(QObject):
    done = Signal(object, int, object, float)  # path, index, QImage | None, skew


class PageView(QGraphicsView):
    """Graphics view with wheel/pinch zoom, a magnifier and an area selection tool."""

    zoom_changed = Signal(float)
    selection_finished = Signal(QPoint)  # global position for the action menu

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
        self.select_mode = False
        self.bounds = QRectF()  # page image rectangle in scene coordinates
        self.selection: QGraphicsRectItem | None = None
        self._origin: QPointF | None = None
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

    # --- area selection ------------------------------------------------------------------

    def _to_page(self, pos: QPointF) -> QPointF:
        point = self.mapToScene(pos.toPoint())
        b = self.bounds
        return QPointF(
            min(max(point.x(), b.left()), b.right()), min(max(point.y(), b.top()), b.bottom())
        )

    def clear_selection(self) -> None:
        """Remove the selection (call before ``scene().clear()``, which deletes it)."""
        if self.selection is not None:
            self.scene().removeItem(self.selection)
            self.selection = None
        self._origin = None

    def selection_rect(self) -> QRectF | None:
        return self.selection.rect() if self.selection is not None else None

    def _start_selection(self, pos: QPointF) -> None:
        self.clear_selection()
        self._origin = self._to_page(pos)
        item = QGraphicsRectItem(QRectF(self._origin, self._origin))
        accent = theme.color("accent")
        pen = QPen(accent, 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        item.setPen(pen)
        fill = QColor(accent)
        fill.setAlpha(40)
        item.setBrush(fill)
        item.setZValue(10)
        self.scene().addItem(item)
        self.selection = item

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None and self.selection is not None:
            self.selection.setRect(
                QRectF(self._origin, self._to_page(event.position())).normalized()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None and event.button() == Qt.MouseButton.LeftButton:
            self._origin = None
            rect = self.selection_rect()
            if rect is None or min(rect.width(), rect.height()) < _MIN_SELECTION:
                self.clear_selection()
            else:
                self.selection_finished.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        rect = self.selection_rect()
        if rect is not None and rect.contains(self.mapToScene(event.pos())):
            self.selection_finished.emit(event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.selection is not None:
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self.select_mode
            and event.button() == Qt.MouseButton.LeftButton
            and not self.bounds.isEmpty()
        ):
            self._start_selection(event.position())
            event.accept()
            return
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
    copy_selection_requested = Signal()
    save_selection_requested = Signal()

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
        self._skew = 0.0
        self._shown: tuple[Path, int] | None = None  # page currently in the scene

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
        self.select_btn = self._tool("icon_crop", S.SELECT_TOOL, None, checkable=True)
        tools.addButton(self.hand_btn)
        tools.addButton(self.magnifier_btn)
        tools.addButton(self.select_btn)
        self.hand_btn.toggled.connect(self._set_hand)
        self.magnifier_btn.toggled.connect(self._set_magnifier)
        self.select_btn.toggled.connect(self._set_select)
        self.view.selection_finished.connect(self._selection_menu)
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
            self.select_btn,
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
            self.select_btn.setChecked(False)
        self.view.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag if on else QGraphicsView.DragMode.NoDrag
        )

    def _set_magnifier(self, on: bool) -> None:
        if on:
            self.hand_btn.setChecked(False)
            self.select_btn.setChecked(False)
        self.view.magnifier = on
        self.view.viewport().setCursor(
            Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor
        )

    def _set_select(self, on: bool) -> None:
        if on:
            self.hand_btn.setChecked(False)
            self.magnifier_btn.setChecked(False)
        else:
            self.view.clear_selection()
        self.view.select_mode = on
        self.view.viewport().setCursor(
            Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor
        )

    def _selection_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # Slots must be callables: a bare SignalInstance raises TypeError when triggered.
        menu.addAction(
            icons.icon("icon_copy"), S.SELECTION_COPY, self.copy_selection_requested.emit
        )
        menu.addAction(
            icons.icon("icon_save"), S.SELECTION_SAVE, self.save_selection_requested.emit
        )
        menu.addSeparator()
        menu.addAction(S.SELECTION_CLEAR, self.view.clear_selection)
        menu.popup(pos)

    def selection_image(self) -> QImage | None:
        """The selected area cut from the page rendered at :data:`CROP_DPI`.

        PDF pages are rendered again at a higher resolution than the preview;
        image files are cut at their own resolution. A rotation of the preview
        by a multiple of 90 degrees is applied to the result.
        """
        rect = self.view.selection_rect()
        if rect is None or self._path is None or self.view.bounds.isEmpty():
            return None
        bounds = self.view.bounds
        try:
            with open_document(self._path) as doc:
                page = doc.render(self._index, CROP_DPI)
        except LokalOcrError:
            return None
        width, height = page.image.size
        box = (
            round(rect.left() / bounds.width() * width),
            round(rect.top() / bounds.height() * height),
            round(rect.right() / bounds.width() * width),
            round(rect.bottom() / bounds.height() * height),
        )
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            return None
        image = pil_to_qimage(page.image.crop(box))
        turns = round(self.view.rotation / 90)
        if abs(self.view.rotation - turns * 90) < 0.01 and turns % 4:
            image = image.transformed(QTransform().rotate(90 * (turns % 4)))
        dots_per_metre = round(page.dpi / 0.0254)
        image.setDotsPerMeterX(dots_per_metre)
        image.setDotsPerMeterY(dots_per_metre)
        return image

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
        self._shown = None
        self.view.clear_selection()
        self.view.bounds = QRectF()
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
        if key == self._shown and self._pixmap_item is not None:
            # Same page again (the window refreshes it on queue updates): keep the
            # scene, so the selection, zoom and deskew survive; overlays may change.
            self._draw_overlay()
        elif key in self._cache:
            self._cache.move_to_end(key)
            image, skew = self._cache[key]
            self._show_image(key, image, skew)
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
        if path != self._path or index != self._index or (path, index) == self._shown:
            return
        if image is None:
            self.view.hide()
            self.placeholder.setText(S.PREVIEW_FAILED)
            self.placeholder.show()
            return
        self._show_image((path, index), image, skew)

    def _show_image(self, key: tuple[Path, int], image: QImage, skew: float) -> None:
        self._shown = key
        self._skew = skew
        self.deskew_btn.setEnabled(abs(skew) >= 0.05)
        scene = self.view.scene()
        self.view.clear_selection()
        scene.clear()
        self._overlay_items = []
        self._pixmap_item = scene.addPixmap(QPixmap.fromImage(image))
        self.view.bounds = QRectF(image.rect())
        scene.setSceneRect(QRectF(image.rect()).adjusted(-40, -40, 40, 40))
        self.view.show()
        self.placeholder.hide()
        if self.view.fit_mode:
            self.view.fit()
        else:
            self.view.apply_transform()
        self._draw_overlay()

    # --- block overlay (Podgląd tab) ------------------------------------------------------

    def set_overlay_visible(self, visible: bool) -> None:
        self._overlay_visible = visible
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
        boxes = [b.bbox for b in page.blocks if b.bbox is not None] if self._overlay_visible else []
        for bbox in boxes:
            rect = QGraphicsRectItem(bbox.x * sx, bbox.y * sy, bbox.width * sx, bbox.height * sy)
            pen = QPen(accent, 1.2)
            pen.setCosmetic(True)
            rect.setPen(pen)
            fill = QColor(accent)
            fill.setAlpha(22)
            rect.setBrush(fill)
            scene.addItem(rect)
            self._overlay_items.append(rect)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._cache.clear()
