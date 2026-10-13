"""Zone 5: text result with layout switch, search, copy and status line (§7.3).

While a document is processed the panel shows the stage, progress, ETA and a
cancel button instead.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lokalocr.errors import ErrorCode
from lokalocr.model import Document
from lokalocr.pipeline import ProgressEvent
from lokalocr.textview import TextLayout, render
from lokalocr.ui import icons, theme
from lokalocr.ui import strings_pl as S
from lokalocr.ui.widgets.basic import muted_label

MONO_FAMILIES = ("Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "Liberation Mono")


def mono_font(point_size: float) -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    families = set(QFontDatabase.families())
    for family in MONO_FAMILIES:
        if family in families:
            font.setFamily(family)
            break
    font.setPointSizeF(point_size)
    return font


class ResultPanel(QFrame):
    cancel_requested = Signal()
    copied = Signal()

    PAGE_EMPTY, PAGE_PROGRESS, PAGE_ERROR, PAGE_RESULT = range(4)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._document: Document | None = None
        self._layout: TextLayout = "original"
        self._wrap = False
        self._hits: list[QTextCursor] = []
        self._hit_index = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # Toolbar: layout switch, search, more
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.original_btn = QPushButton(S.LAYOUT_ORIGINAL)
        self.simple_btn = QPushButton(S.LAYOUT_SIMPLIFIED)
        group = QButtonGroup(self)
        for btn in (self.original_btn, self.simple_btn):
            btn.setCheckable(True)
            btn.setProperty("segment", True)
            group.addButton(btn)
            bar.addWidget(btn)
        self.original_btn.setChecked(True)
        self.original_btn.setToolTip(S.LAYOUT_ORIGINAL_TIP)
        self.simple_btn.setToolTip(S.LAYOUT_SIMPLIFIED_TIP)
        self.original_btn.toggled.connect(self._on_original_toggled)
        self.simple_btn.toggled.connect(self._on_simple_toggled)
        bar.addSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(S.SEARCH_PLACEHOLDER)
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName(S.SEARCH_PLACEHOLDER)
        self.search.textChanged.connect(self._run_search)
        self.search.returnPressed.connect(self.next_hit)
        bar.addWidget(self.search, 1)
        self.prev_btn = QToolButton()
        self.prev_btn.setToolTip(S.SEARCH_PREV)
        self.prev_btn.clicked.connect(self.prev_hit)
        self.next_btn = QToolButton()
        self.next_btn.setToolTip(S.SEARCH_NEXT)
        self.next_btn.clicked.connect(self.next_hit)
        self.more_btn = QToolButton()
        self.more_btn.setToolTip(S.MORE_OPTIONS)
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more_btn)
        select_all = QAction(S.SELECT_ALL, menu)
        select_all.triggered.connect(self._select_all)
        self.wrap_action = QAction(S.WRAP_LINES, menu)
        self.wrap_action.setCheckable(True)
        self.wrap_action.toggled.connect(self.set_wrap)
        menu.addAction(select_all)
        menu.addAction(self.wrap_action)
        self.more_btn.setMenu(menu)
        for b in (self.prev_btn, self.next_btn, self.more_btn):
            bar.addWidget(b)
        self.toolbar = QWidget()
        self.toolbar.setLayout(bar)
        outer.addWidget(self.toolbar)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # Empty state
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch()
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel(S.EMPTY_RESULT_TITLE)
        self.empty_title.setProperty("heading", True)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint = muted_label(S.EMPTY_RESULT_HINT)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        el.addWidget(self.empty_icon)
        el.addWidget(self.empty_title)
        el.addWidget(self.empty_hint)
        el.addStretch()
        self.stack.addWidget(empty)

        # Progress state
        progress = QWidget()
        pl = QVBoxLayout(progress)
        pl.addStretch()
        self.progress_title = QLabel(S.PROCESSING_TITLE)
        self.progress_title.setProperty("heading", True)
        self.progress_stage = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_pct = muted_label("0%")
        row = QHBoxLayout()
        row.addWidget(self.progress_bar, 1)
        row.addWidget(self.progress_pct)
        self.progress_eta = muted_label(S.eta_text(None), small=True)
        self.cancel_btn = QPushButton(S.CANCEL)
        self.cancel_btn.setProperty("danger", True)
        self.cancel_btn.setToolTip(S.CANCEL_TIP)
        self.cancel_btn.clicked.connect(self.cancel_requested)
        pl.addWidget(self.progress_title)
        pl.addWidget(self.progress_stage)
        pl.addLayout(row)
        pl.addWidget(self.progress_eta)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        pl.addLayout(btn_row)
        pl.addStretch()
        self.stack.addWidget(progress)

        # Error state
        error = QWidget()
        erl = QVBoxLayout(error)
        erl.addStretch()
        self.error_icon = QLabel()
        self.error_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_text = QLabel("")
        self.error_text.setWordWrap(True)
        self.error_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        erl.addWidget(self.error_icon)
        erl.addWidget(self.error_text)
        erl.addStretch()
        self.stack.addWidget(error)

        # Result state
        result = QWidget()
        rl = QVBoxLayout(result)
        rl.setContentsMargins(0, 0, 0, 0)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName(S.RESULT_TEXT_NAME)
        self.text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.installEventFilter(self)
        self.copy_corner = QToolButton(self.text)
        self.copy_corner.setToolTip(S.COPY_VISIBLE)
        self.copy_corner.clicked.connect(self.copy_text)
        rl.addWidget(self.text)
        self.stack.addWidget(result)

        # Status line + copy button
        status = QHBoxLayout()
        self.status = muted_label("", small=True)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_btn = QPushButton(S.COPY_TEXT)
        self.copy_btn.setToolTip(S.COPY_TEXT_TIP)
        self.copy_btn.clicked.connect(self.copy_text)
        status.addWidget(self.status, 1)
        status.addWidget(self.copy_btn)
        outer.addLayout(status)

        self.refresh_icons()
        self.show_empty()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # §7.9: Ctrl+C on the text copies the selection, or everything if
        # nothing is selected.
        if (
            watched is self.text
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Copy)
        ):
            self.copy_text()
            return True
        return super().eventFilter(watched, event)

    def _on_original_toggled(self, on: bool) -> None:
        if on:
            self.set_layout("original")

    def _on_simple_toggled(self, on: bool) -> None:
        if on:
            self.set_layout("simplified")

    def _select_all(self) -> None:
        self.text.selectAll()

    # --- appearance ------------------------------------------------------------

    def refresh_icons(self) -> None:
        self.prev_btn.setIcon(icons.icon("icon_prev"))
        self.next_btn.setIcon(icons.icon("icon_next"))
        self.more_btn.setIcon(icons.icon("icon_more"))
        self.copy_corner.setIcon(icons.icon("icon_copy"))
        self.copy_btn.setIcon(icons.icon("icon_copy"))
        self.empty_icon.setPixmap(icons.pixmap("icon_tab_text", 40, "text_muted"))
        self.error_icon.setPixmap(icons.pixmap("status_error", 36, "danger"))
        self.text.setFont(mono_font(max(9.0, self.font().pointSizeF())))
        self._highlight_hits()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        vp = self.text.viewport()
        self.copy_corner.move(vp.width() - 34, 6)

    # --- states ------------------------------------------------------------------

    def _set_result_controls(self, enabled: bool) -> None:
        for w in (self.toolbar, self.copy_btn):
            w.setEnabled(enabled)

    def show_empty(
        self, title: str = S.EMPTY_RESULT_TITLE, hint: str = S.EMPTY_RESULT_HINT
    ) -> None:
        self._document = None
        self.empty_title.setText(title)
        self.empty_hint.setText(hint)
        self.text.clear()
        self.status.setText("")
        self._set_result_controls(False)
        self.stack.setCurrentIndex(self.PAGE_EMPTY)

    def show_waiting(self, name: str) -> None:
        self.show_empty(S.WAITING_TITLE, S.waiting_hint(name))

    def show_progress(self, event: ProgressEvent | None, title: str = S.PROCESSING_TITLE) -> None:
        self._set_result_controls(False)
        self.stack.setCurrentIndex(self.PAGE_PROGRESS)
        self.progress_title.setText(title)
        if event is None:
            self.progress_stage.setText(S.STAGE_LABELS["loading"])
            self.progress_bar.setValue(0)
            self.progress_pct.setText("0%")
            self.progress_eta.setText(S.eta_text(None))
            return
        stage = S.STAGE_LABELS[event.stage]
        if event.page_count > 1 and event.page:
            stage = f"{stage} {S.page_of(event.page, event.page_count)}"
        self.progress_stage.setText(stage)
        self.progress_bar.setValue(round(event.percent * 10))
        self.progress_pct.setText(f"{round(event.percent)}%")
        self.progress_eta.setText(S.eta_text(event.eta_seconds))
        self.status.setText("")

    def show_error(self, code: ErrorCode) -> None:
        self._document = None
        self.error_text.setText(S.error_message(code))
        self.status.setText("")
        self._set_result_controls(False)
        self.stack.setCurrentIndex(self.PAGE_ERROR)

    def show_document(self, document: Document) -> None:
        self._document = document
        self._set_result_controls(True)
        self.stack.setCurrentIndex(self.PAGE_RESULT)
        self._render()

    # --- content -------------------------------------------------------------------

    @property
    def document(self) -> Document | None:
        return self._document

    @property
    def layout_mode(self) -> TextLayout:
        return self._layout

    def set_layout(self, layout: TextLayout) -> None:
        self._layout = layout
        (self.original_btn if layout == "original" else self.simple_btn).setChecked(True)
        if self._document is not None:
            self._render()

    def set_wrap(self, wrap: bool) -> None:
        self._wrap = wrap
        self.wrap_action.setChecked(wrap)
        self.text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if wrap else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def visible_text(self) -> str:
        return self.text.toPlainText()

    def _render(self) -> None:
        assert self._document is not None
        self.text.setPlainText(render(self._document, self._layout))
        self._update_status()
        self._run_search(self.search.text())

    def _update_status(self) -> None:
        doc = self._document
        if doc is None:
            self.status.setText("")
            return
        words = len(self.visible_text().split())
        self.status.setText(S.status_line(doc.page_count, words, doc.lang, doc.mean_confidence))

    def copy_text(self) -> None:
        cursor = self.text.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n") if cursor.hasSelection() else ""
        QApplication.clipboard().setText(text or self.visible_text())
        self.copied.emit()

    # --- search ----------------------------------------------------------------------

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _run_search(self, needle: str) -> None:
        self._hits = []
        self._hit_index = -1
        if needle and self._document is not None:
            doc = self.text.document()
            cursor = QTextCursor(doc)
            while True:
                cursor = doc.find(needle, cursor, QTextDocument.FindFlag(0))
                if cursor.isNull():
                    break
                self._hits.append(QTextCursor(cursor))
        self._highlight_hits()
        if self._hits:
            self._go_to(0)
        self._update_search_status()

    def _highlight_hits(self) -> None:
        selections = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(theme.tokens().highlight))
        for hit in self._hits:
            sel = QTextEdit.ExtraSelection()
            sel.cursor = hit
            sel.format = fmt
            selections.append(sel)
        self.text.setExtraSelections(selections)

    def _go_to(self, i: int) -> None:
        if not self._hits:
            return
        self._hit_index = i % len(self._hits)
        self.text.setTextCursor(self._hits[self._hit_index])
        self.text.ensureCursorVisible()
        self._update_search_status()

    def _update_search_status(self) -> None:
        if not self.search.text():
            self._update_status()
            return
        if not self._hits:
            self.status.setText(S.SEARCH_NO_HITS)
        else:
            self.status.setText(S.search_hits(self._hit_index + 1, len(self._hits)))

    def next_hit(self) -> None:
        self._go_to(self._hit_index + 1)

    def prev_hit(self) -> None:
        self._go_to(self._hit_index - 1)
