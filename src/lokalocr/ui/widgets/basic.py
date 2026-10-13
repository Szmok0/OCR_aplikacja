"""Small reusable widgets: toggle switch, drop zone, offline badge, toast."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lokalocr.loader import SUPPORTED_EXTENSIONS
from lokalocr.ui import icons, theme
from lokalocr.ui import strings_pl as S


def set_prop(widget: QWidget, name: str, value: object) -> None:
    """Set a dynamic property used by the style sheet and re-polish."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def muted_label(text: str = "", small: bool = False) -> QLabel:
    label = QLabel(text)
    label.setProperty("muted", True)
    if small:
        font = label.font()
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1))
        label.setFont(font)
    return label


def primary_button(text: str, icon_name: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("primary", True)
    if icon_name:
        button.setIcon(icons.icon(icon_name, "on_accent"))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class ToggleSwitch(QAbstractButton):
    """iOS-style switch (§7.7 'przełączniki w stylu toggle'), keyboard accessible."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(38, 22)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._pos = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, (self.height() - 20) / 2, 36, 20)
        on = QColor(t.accent)
        off = QColor(t.border)
        track = QColor(
            round(off.red() + (on.red() - off.red()) * self._pos),
            round(off.green() + (on.green() - off.green()) * self._pos),
            round(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 10, 10)
        p.setBrush(QColor("#FFFFFF"))
        x = r.left() + 2 + (r.width() - 20) * self._pos
        p.drawEllipse(QRectF(x, r.top() + 2, 16, 16))
        if self.hasFocus():
            pen = QColor(t.accent)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 11, 11)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
        else:
            super().keyPressEvent(event)


def dropped_paths(event: QDropEvent | QDragEnterEvent) -> list[Path]:
    mime = event.mimeData()
    if not mime.hasUrls():
        return []
    return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]


def accepts(paths: list[Path]) -> bool:
    return any(p.is_dir() or p.suffix.lower() in SUPPORTED_EXTENSIONS for p in paths)


class DropZone(QFrame):
    """Zone 1 drop area: dashed border, icon, hints and the main 'Wybierz pliki…' button."""

    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(S.DROP_TITLE)
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        formats = muted_label(S.DROP_FORMATS, small=True)
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = muted_label(S.DROP_HINT, small=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.button = primary_button(S.CHOOSE_FILES, "btn_add")
        self.button.setToolTip(S.CHOOSE_FILES_TIP)
        self.button.clicked.connect(self.browse_requested)
        layout.addWidget(self.icon)
        layout.addSpacing(4)
        layout.addWidget(title)
        layout.addWidget(formats)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addWidget(self.button)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        self.icon.setPixmap(icons.pixmap("file_drop", 36, "accent"))
        self.button.setIcon(icons.icon("btn_add", "on_accent"))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if accepts(dropped_paths(event)):
            event.acceptProposedAction()
            set_prop(self, "dragActive", True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: object) -> None:
        set_prop(self, "dragActive", False)

    def dropEvent(self, event: QDropEvent) -> None:
        set_prop(self, "dragActive", False)
        paths = dropped_paths(event)
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)


class OfflineBadge(QWidget):
    """Permanent 'Offline — brak połączeń sieciowych' marker with a green dot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OfflineBadge")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.label = QLabel(S.OFFLINE_BADGE)
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.setToolTip(S.OFFLINE_TIP)
        self.setAccessibleName(S.OFFLINE_BADGE)
        self.refresh()

    def refresh(self) -> None:
        self.dot.setStyleSheet(f"background: {theme.tokens().success}; border-radius: 5px;")


class Toast(QFrame):
    """Short in-window notification with an optional action (§7.3 zone 6)."""

    action_triggered = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        self.text = QLabel()
        self.action = QPushButton()
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self.action_triggered)
        self.action.clicked.connect(self.hide)
        layout.addWidget(self.text)
        layout.addWidget(self.action)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, action: str | None = None, msec: int = 6000) -> None:
        self.text.setText(text)
        self.action.setVisible(bool(action))
        self.action.setText(action or "")
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 84)
        self.show()
        self.raise_()
        self._timer.start(msec)
