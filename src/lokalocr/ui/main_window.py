"""Main window (§7.3): header, queue + quick settings, workspace, result panel, action bar."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QMouseEvent,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lokalocr import tempdir
from lokalocr.engines.base import OcrEngine
from lokalocr.errors import ErrorCode, LokalOcrError
from lokalocr.exporters.common import OutputExistsError, default_output_name
from lokalocr.exporters.docx import export_docx
from lokalocr.exporters.html import export_html
from lokalocr.exporters.markdown import export_markdown
from lokalocr.exporters.pdf_text import PdfRenderer, export_searchable_pdf
from lokalocr.exporters.txt import export_txt
from lokalocr.loader import SUPPORTED_EXTENSIONS, detect_format
from lokalocr.model import Document
from lokalocr.pipeline import LANGUAGES, ProcessOptions, ProgressEvent
from lokalocr.preprocess import PreprocessOptions
from lokalocr.ui import icons
from lokalocr.ui import strings_pl as S
from lokalocr.ui.queue_model import ITEM_ROLE, QueueItem, QueueModel, Status
from lokalocr.ui.widgets.basic import (
    DropZone,
    OfflineBadge,
    Toast,
    ToggleSwitch,
    accepts,
    dropped_paths,
    muted_label,
)
from lokalocr.ui.widgets.preview import PagePreview
from lokalocr.ui.widgets.queue_delegate import QueueDelegate, more_button_rect
from lokalocr.ui.widgets.result_panel import ResultPanel
from lokalocr.ui.worker import WRITE_FAILED, ExportController, ProcessingController

_log = logging.getLogger(__name__)

TAB_TEXT, TAB_PREVIEW, TAB_IMAGES = range(3)
FORMATS = ("docx", "txt", "pdf", "md", "html")
DEFAULT_FORMAT = "docx"
FORMAT_ICONS = {"txt": "file_txt", "pdf": "file_pdf", "md": "file_markdown", "html": "file_html"}


class QueueList(QListView):
    """Queue view; clicking the '⋯' area of an item opens its menu."""

    def __init__(self, on_menu: Callable[[QueueItem, QPoint], None]) -> None:
        super().__init__()
        self.setObjectName("QueueList")
        self._on_menu = on_menu
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(QueueDelegate(self))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setAccessibleName(S.QUEUE_TITLE)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            rect = self.visualRect(index)
            if more_button_rect(rect).contains(event.position().toPoint()):
                self.setCurrentIndex(index)
                item = index.data(ITEM_ROLE)
                self._on_menu(
                    item, self.viewport().mapToGlobal(more_button_rect(rect).bottomLeft())
                )
                return
        super().mousePressEvent(event)

    def _context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        if index.isValid():
            self.setCurrentIndex(index)
            self._on_menu(index.data(ITEM_ROLE), self.viewport().mapToGlobal(pos))


class MainWindow(QMainWindow):
    def __init__(
        self, engine_factory: Callable[[], OcrEngine], full_mode_available: bool = False
    ) -> None:
        super().__init__()
        self.setWindowTitle(S.APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setAcceptDrops(True)
        self.resize(1360, 860)
        self.setMinimumSize(QSize(980, 620))
        self.full_mode_available = full_mode_available

        self.queue = QueueModel()
        self.controller = ProcessingController(engine_factory)
        self.controller.progress.connect(self._on_progress)
        self.controller.finished.connect(self._on_finished)
        self.controller.failed.connect(self._on_failed)
        self.controller.probed.connect(self._on_probed)
        self.controller.probe_failed.connect(self._on_probe_failed)
        self.exporter = ExportController()
        self.exporter.progress.connect(self._on_export_progress)
        self.exporter.finished.connect(self._on_export_finished)
        self.exporter.failed.connect(self._on_export_failed)
        self._last_dir = Path.home()
        self._closing = False
        self._remove_after_cancel = False

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(10)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)
        self.splitter.addWidget(self._build_left())
        self.workspace = self._build_workspace()
        self.splitter.addWidget(self.workspace)
        self.result = ResultPanel()
        self.result.cancel_requested.connect(self.cancel_current)
        self.result.setMinimumWidth(320)
        self.result.copied.connect(self._on_copied)
        self.splitter.addWidget(self.result)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setSizes([290, 560, 480])
        body_layout.addWidget(self.splitter, 1)
        body_layout.addWidget(self._build_action_bar())
        root.addWidget(body, 1)
        self.setCentralWidget(central)

        self.toast = Toast(central)
        self.toast.action_triggered.connect(self._show_last_saved)
        self._last_saved: Path | None = None

        self._install_shortcuts()
        self._update_actions()
        self._sized = False
        # Start on the main path (§7.2): the file picker, not the header.
        self.drop_zone.button.setFocus()

    # --- construction ------------------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("AppHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        self.logo = QLabel()
        self.logo.setPixmap(icons.app_pixmap(36))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(S.APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QLabel(S.APP_SUBTITLE)
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addWidget(self.logo)
        layout.addSpacing(8)
        layout.addLayout(titles)
        layout.addStretch()
        self.offline_badge = OfflineBadge()
        layout.addWidget(self.offline_badge)
        layout.addSpacing(16)
        self.settings_btn = QPushButton(S.SETTINGS)
        self.settings_btn.setToolTip(S.SETTINGS_TIP)
        self.settings_btn.clicked.connect(self.open_settings)
        self.settings_btn.setIcon(icons.icon("icon_settings"))
        self.help_btn = QPushButton(S.HELP)
        self.help_btn.setToolTip(S.HELP_TIP)
        self.help_btn.clicked.connect(self.open_help)
        self.help_btn.setIcon(icons.icon("icon_help"))
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.help_btn)
        return header

    def _build_left(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self.add_paths)
        self.drop_zone.browse_requested.connect(self.browse_files)
        layout.addWidget(self.drop_zone)

        queue_panel = QFrame()
        queue_panel.setObjectName("Panel")
        ql = QVBoxLayout(queue_panel)
        ql.setContentsMargins(10, 10, 10, 10)
        head = QHBoxLayout()
        self.queue_title = QLabel(S.queue_title(0))
        self.queue_title.setProperty("heading", True)
        self.clear_btn = QPushButton(S.CLEAR)
        self.clear_btn.setProperty("link", True)
        self.clear_btn.setToolTip(S.CLEAR_TIP)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_queue)
        head.addWidget(self.queue_title)
        head.addStretch()
        head.addWidget(self.clear_btn)
        ql.addLayout(head)
        self.queue_view = QueueList(self._show_item_menu)
        self.queue_view.setModel(self.queue)
        self.queue_view.selectionModel().currentChanged.connect(self._on_current_changed)
        self.queue_empty = muted_label(S.QUEUE_EMPTY, small=True)
        self.queue_empty.setWordWrap(True)
        self.queue_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ql.addWidget(self.queue_view, 1)
        ql.addWidget(self.queue_empty, 1)
        layout.addWidget(queue_panel, 1)

        layout.addWidget(self._build_quick_settings())
        return panel

    def _build_quick_settings(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)
        title = QLabel(S.QUICK_SETTINGS)
        title.setProperty("heading", True)
        layout.addWidget(title)

        layout.addWidget(muted_label(S.OCR_LANGUAGE, small=True))
        self.lang_combo = QComboBox()
        for code in LANGUAGES:
            self.lang_combo.addItem(S.LANGUAGE_LABELS[code], code)
        self.lang_combo.setAccessibleName(S.OCR_LANGUAGE)
        layout.addWidget(self.lang_combo)

        layout.addWidget(muted_label(S.WORK_MODE, small=True))
        modes = QHBoxLayout()
        self.basic_radio = QRadioButton(S.MODE_BASIC)
        self.full_radio = QRadioButton(S.MODE_FULL)
        self.basic_radio.setChecked(True)
        self.basic_radio.setToolTip(S.MODE_BASIC_TIP)
        group = QButtonGroup(panel)
        group.addButton(self.basic_radio)
        group.addButton(self.full_radio)
        if self.full_mode_available:
            self.full_radio.setToolTip(S.MODE_FULL_TIP)
        else:
            self.full_radio.setEnabled(False)
            self.full_radio.setToolTip(S.MODE_FULL_UNAVAILABLE)
        modes.addWidget(self.basic_radio)
        modes.addWidget(self.full_radio)
        modes.addStretch()
        layout.addLayout(modes)

        auto = QHBoxLayout()
        auto_label = QLabel(S.AUTO_PREPROCESS)
        self.preprocess_toggle = ToggleSwitch()
        self.preprocess_toggle.setChecked(True)
        self.preprocess_toggle.setToolTip(S.AUTO_PREPROCESS_TIP)
        self.preprocess_toggle.setAccessibleName(S.AUTO_PREPROCESS)
        auto_label.setBuddy(self.preprocess_toggle)
        auto.addWidget(auto_label, 1)
        auto.addWidget(self.preprocess_toggle)
        layout.addLayout(auto)
        return panel

    def _build_workspace(self) -> QWidget:
        """Zones 3 and 4: view tabs, structure button, page preview / image gallery."""
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)
        head = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.addTab(S.TAB_TEXT)
        self.tabs.addTab(S.TAB_PREVIEW)
        self.tabs.addTab(S.tab_images(0))
        self.tabs.setTabToolTip(TAB_TEXT, S.TAB_TEXT_TIP)
        self.tabs.setTabToolTip(TAB_PREVIEW, S.TAB_PREVIEW_TIP)
        self.tabs.setTabToolTip(TAB_IMAGES, S.IMAGES_UNAVAILABLE)
        self.tabs.setTabEnabled(TAB_IMAGES, False)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        head.addWidget(self.tabs)
        head.addStretch()
        self.structure_btn = QPushButton(S.STRUCTURE)
        self.structure_btn.setToolTip(S.STRUCTURE_UNAVAILABLE)
        self.structure_btn.setEnabled(False)
        self.structure_btn.clicked.connect(self.open_structure)
        head.addWidget(self.structure_btn)
        layout.addLayout(head)

        self.workspace_stack = QStackedWidget()
        self.preview = PagePreview()
        self.workspace_stack.addWidget(self.preview)
        self.images_placeholder = muted_label(S.IMAGES_UNAVAILABLE)
        self.images_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.workspace_stack.addWidget(self.images_placeholder)
        layout.addWidget(self.workspace_stack, 1)
        return panel

    def _build_action_bar(self) -> QWidget:
        """Zone 6: save buttons and output options."""
        bar = QFrame()
        bar.setObjectName("Panel")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.save_main_btn = QToolButton()
        self.save_main_btn.setText(S.save_as(DEFAULT_FORMAT))
        self.save_main_btn.setProperty("primary", True)
        self.save_main_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.save_main_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.save_main_btn.setToolTip(f"{S.FORMAT_TIPS[DEFAULT_FORMAT]} (Ctrl+S)")
        self.save_main_btn.clicked.connect(lambda: self.save(DEFAULT_FORMAT))
        menu = QMenu(self.save_main_btn)
        for fmt in FORMATS:
            action = menu.addAction(S.FORMAT_LABELS[fmt])
            action.setToolTip(S.FORMAT_TIPS[fmt])
            action.triggered.connect(lambda _=False, f=fmt: self.save(f))
        self.save_main_btn.setMenu(menu)
        layout.addWidget(self.save_main_btn)

        self.format_buttons: dict[str, QPushButton] = {}
        for fmt in ("txt", "pdf", "md", "html"):
            button = QPushButton(S.FORMAT_LABELS[fmt])
            button.setToolTip(S.FORMAT_TIPS[fmt])
            button.setProperty("iconName", FORMAT_ICONS[fmt])
            button.clicked.connect(lambda _=False, f=fmt: self.save(f))
            self.format_buttons[fmt] = button
            layout.addWidget(button)
        self.open_images_btn = QPushButton(S.open_images(0))
        self.open_images_btn.setProperty("iconName", "icon_folder_open")
        self.open_images_btn.setToolTip(S.IMAGES_UNAVAILABLE)
        self.open_images_btn.setEnabled(False)
        layout.addWidget(self.open_images_btn)
        layout.addStretch()

        options = QVBoxLayout()
        options.setSpacing(2)
        options.addWidget(muted_label(S.OUTPUT_OPTIONS, small=True))
        row = QHBoxLayout()
        self.clean_text_cb = QCheckBox(S.CLEAN_TEXT_ALWAYS)
        self.clean_text_cb.setChecked(True)
        self.clean_text_cb.setEnabled(False)
        self.clean_text_cb.setToolTip(S.CLEAN_TEXT_TIP)
        self.keep_structure_cb = QCheckBox(S.KEEP_STRUCTURE)
        self.keep_structure_cb.setChecked(True)
        self.keep_structure_cb.setToolTip(S.KEEP_STRUCTURE_TIP)
        self.structure_info = QLabel()
        self.structure_info.setToolTip(S.KEEP_STRUCTURE_TIP)
        row.addWidget(self.clean_text_cb)
        row.addSpacing(8)
        row.addWidget(self.keep_structure_cb)
        row.addWidget(self.structure_info)
        options.addLayout(row)
        layout.addLayout(options)
        self._refresh_action_icons()
        return bar

    def _refresh_action_icons(self) -> None:
        self.save_main_btn.setIcon(icons.icon("icon_save", "on_accent"))
        self.save_main_btn.setIconSize(QSize(16, 16))
        for button in (*self.format_buttons.values(), self.open_images_btn):
            name = button.property("iconName")
            if name:
                button.setIcon(icons.icon(str(name)))
        self.structure_info.setPixmap(icons.pixmap("icon_info", 16, "text_muted"))

    def _install_shortcuts(self) -> None:
        def bind(
            seq: QKeySequence | QKeySequence.StandardKey | str, slot: Callable[[], object]
        ) -> None:
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(slot)

        bind(QKeySequence.StandardKey.Open, self.browse_files)
        bind(QKeySequence.StandardKey.Save, lambda: self.save(DEFAULT_FORMAT))
        bind(QKeySequence.StandardKey.MoveToPreviousPage, self.preview.prev_page)
        bind(QKeySequence.StandardKey.MoveToNextPage, self.preview.next_page)
        bind(QKeySequence.StandardKey.ZoomIn, self.preview.view.zoom_in)
        bind(QKeySequence.StandardKey.ZoomOut, self.preview.view.zoom_out)
        bind(QKeySequence.StandardKey.Find, self.result.focus_search)
        bind("Esc", self.cancel_current)
        bind("F1", self.open_help)
        bind("Ctrl+,", self.open_settings)
        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.queue_view)
        delete.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete.activated.connect(self._remove_current)

    # --- queue -------------------------------------------------------------------

    def options(self) -> ProcessOptions:
        return ProcessOptions(
            lang=str(self.lang_combo.currentData()),
            mode="full" if self.full_radio.isChecked() else "basic",
            preprocess=PreprocessOptions(enabled=self.preprocess_toggle.isChecked()),
        )

    def browse_files(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(
            self, S.CHOOSE_FILES_DIALOG, str(self._last_dir), f"{S.FILE_FILTER} ({patterns})"
        )
        if files:
            self.add_paths([Path(f) for f in files])

    def add_paths(self, paths: list[Path]) -> None:
        expanded: list[Path] = []
        for path in paths:
            if path.is_dir():
                expanded.extend(
                    sorted(
                        p
                        for p in path.iterdir()
                        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
                    )
                )
            else:
                expanded.append(path)
        rejected = 0
        first_new: QueueItem | None = None
        for path in expanded:
            if self.queue.contains_path(path):
                continue
            try:
                kind = detect_format(path)
            except LokalOcrError:
                rejected += 1
                continue
            item = QueueItem(
                path=path,
                size_bytes=path.stat().st_size,
                file_kind="pdf" if kind == "pdf" else "image",
            )
            self.queue.add(item)
            self.controller.probe(item.id, path)
            first_new = first_new or item
            self._last_dir = path.parent
        if rejected:
            self.toast.show_message(S.rejected_files(rejected))
        if first_new is not None and not self.queue_view.currentIndex().isValid():
            self.select_item(first_new.id)
        self._update_queue_header()
        self._schedule()

    def select_item(self, item_id: int) -> None:
        row = self.queue.row_of(item_id)
        if row >= 0:
            self.queue_view.setCurrentIndex(self.queue.index(row))

    def current_item(self) -> QueueItem | None:
        index = self.queue_view.currentIndex()
        return index.data(ITEM_ROLE) if index.isValid() else None

    def _show_item_menu(self, item: QueueItem, pos: QPoint) -> None:
        menu = QMenu(self)
        show = menu.addAction(S.MENU_SHOW_RESULT)
        show.setEnabled(item.status is Status.DONE)
        show.triggered.connect(lambda: self.select_item(item.id))
        again = menu.addAction(S.MENU_REPROCESS)
        again.setEnabled(item.status is not Status.PROCESSING)
        again.triggered.connect(lambda: self.reprocess(item.id))
        remove = menu.addAction(S.MENU_REMOVE)
        remove.triggered.connect(lambda: self.remove_item(item.id))
        menu.exec(pos)

    def reprocess(self, item_id: int) -> None:
        item = self.queue.get(item_id)
        if item is None or item.status is Status.PROCESSING:
            return
        item.status = Status.WAITING
        item.paused = False
        item.document = None
        item.error_code = None
        item.progress = 0.0
        self.queue.changed(item_id)
        self._refresh_selected()
        self._schedule()

    def remove_item(self, item_id: int) -> None:
        if self.controller.current_item == item_id:
            self._remove_after_cancel = True
            self.controller.cancel()
            return  # removed once the worker reports the cancellation
        self.queue.remove(item_id)
        self._update_queue_header()
        self._refresh_selected()

    def _remove_current(self) -> None:
        item = self.current_item()
        if item is not None:
            self.remove_item(item.id)

    def clear_queue(self) -> None:
        if len(self.queue) == 0:
            return
        if self.controller.busy:
            self.controller.cancel()
        self.queue.clear()
        tempdir.cleanup()
        self._update_queue_header()
        self._refresh_selected()

    def _update_queue_header(self) -> None:
        n = len(self.queue)
        self.queue_title.setText(S.queue_title(n))
        self.clear_btn.setEnabled(n > 0)
        self.queue_empty.setVisible(n == 0)
        self.queue_view.setVisible(n > 0)

    # --- processing ------------------------------------------------------------------

    def _schedule(self) -> None:
        if self.controller.busy or self._closing:
            return
        item = next(
            (i for i in self.queue.items() if i.status is Status.WAITING and not i.paused), None
        )
        if item is None:
            return
        options = self.options()
        item.status = Status.PROCESSING
        item.progress = 0.0
        item.options = options
        self.queue.changed(item.id)
        self.controller.start(item.id, item.path, options)
        self._refresh_selected()

    def cancel_current(self) -> None:
        """Ask how to cancel (§7.6): keep the file waiting or remove it."""
        if self.exporter.busy:
            self.exporter.cancel()
            return
        item_id = self.controller.current_item
        if item_id is None:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(S.CANCEL)
        box.setText(S.CANCEL_QUESTION)
        keep = box.addButton(S.CANCEL_KEEP, QMessageBox.ButtonRole.AcceptRole)
        remove = box.addButton(S.CANCEL_REMOVE, QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(S.CANCEL_CONTINUE, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        box.exec()
        clicked = box.clickedButton()
        if clicked is keep:
            self.cancel_item(item_id, remove=False)
        elif clicked is remove:
            self.cancel_item(item_id, remove=True)

    def cancel_item(self, item_id: int, *, remove: bool) -> None:
        if self.controller.current_item != item_id:
            return
        self._remove_after_cancel = remove
        self.controller.cancel()

    def _on_progress(self, item_id: int, event: ProgressEvent) -> None:
        item = self.queue.get(item_id)
        if item is None or item.status is not Status.PROCESSING:
            return
        item.progress = event.percent
        item.stage = event.stage
        item.eta_seconds = event.eta_seconds
        if event.page_count:
            item.page_count = event.page_count
        self.queue.changed(item_id)
        if self._is_selected(item_id):
            self.result.show_progress(event)

    def _on_finished(self, item_id: int, document: Document, options: ProcessOptions) -> None:
        item = self.queue.get(item_id)
        if item is not None:
            item.status = Status.DONE
            item.progress = 100.0
            item.document = document
            item.options = options
            item.page_count = document.page_count
            self.queue.changed(item_id)
            if self._is_selected(item_id):
                self._refresh_selected()
        QTimer.singleShot(0, self._schedule)

    def _on_failed(self, item_id: int, code: str) -> None:
        item = self.queue.get(item_id)
        if item is not None:
            error = ErrorCode(code)
            if error is ErrorCode.CANCELLED:
                if self._remove_after_cancel:
                    self.queue.remove(item_id)
                    self._update_queue_header()
                else:
                    # Back to "waiting", but not restarted until the user asks.
                    item.status = Status.WAITING
                    item.progress = 0.0
                    item.paused = True
                    self.queue.changed(item_id)
            else:
                item.status = Status.ERROR
                item.error_code = error
                self.queue.changed(item_id)
            if self._is_selected(item_id):
                self._refresh_selected()
        self._remove_after_cancel = False
        QTimer.singleShot(0, self._schedule)

    def _on_probed(self, item_id: int, pages: int | None, thumb: object) -> None:
        item = self.queue.get(item_id)
        if item is None:
            return
        if item.page_count is None:
            item.page_count = pages
        item.thumbnail = thumb  # type: ignore[assignment]
        self.queue.changed(item_id)

    def _on_probe_failed(self, item_id: int, code: str) -> None:
        item = self.queue.get(item_id)
        if item is None or item.status is not Status.WAITING:
            return
        _ = code  # the full run reports the precise error

    # --- selection / result ------------------------------------------------------------

    def _is_selected(self, item_id: int) -> bool:
        current = self.current_item()
        return current is not None and current.id == item_id

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self._refresh_selected()

    def _refresh_selected(self) -> None:
        item = self.current_item()
        if item is None:
            self.result.show_empty()
            self.preview.clear()
        else:
            pages = item.document.pages if item.document is not None else None
            self.preview.show_document(item.path, item.page_count, pages)
            if self.exporter.current_item == item.id:
                self.result.show_progress(None, title=S.EXPORTING_TITLE)
            elif item.status is Status.DONE and item.document is not None:
                self.result.show_document(item.document)
            elif item.status is Status.PROCESSING:
                self.result.show_progress(None)
            elif item.status is Status.ERROR and item.error_code is not None:
                self.result.show_error(item.error_code)
            else:
                self.result.show_waiting(item.name)
        self._update_actions()

    def _update_actions(self) -> None:
        item = self.current_item()
        has_result = item is not None and item.document is not None
        full = (
            has_result
            and item is not None
            and item.document is not None
            and (item.document.mode == "full")
        )
        self.save_main_btn.setEnabled(has_result)
        for button in self.format_buttons.values():
            button.setEnabled(has_result)
        self.keep_structure_cb.setEnabled(full)
        self.structure_btn.setEnabled(full)
        self.structure_btn.setToolTip(S.STRUCTURE_TIP if full else S.STRUCTURE_UNAVAILABLE)
        image_count = len(item.document.images) if item is not None and item.document else 0
        self.tabs.setTabText(TAB_IMAGES, S.tab_images(image_count))
        self.tabs.setTabEnabled(TAB_IMAGES, full)
        self.tabs.setTabToolTip(TAB_IMAGES, S.TAB_IMAGES_TIP if full else S.IMAGES_UNAVAILABLE)
        self.open_images_btn.setText(S.open_images(image_count))
        self.open_images_btn.setEnabled(False)  # images folder arrives with full mode

    # --- view tabs ----------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        self.workspace_stack.setCurrentIndex(1 if index == TAB_IMAGES else 0)
        self.result.setVisible(index == TAB_TEXT)
        self.preview.set_overlay_visible(index == TAB_PREVIEW)

    def open_structure(self) -> None:
        QMessageBox.information(self, S.STRUCTURE, S.STRUCTURE_UNAVAILABLE)

    # --- saving ------------------------------------------------------------------------

    def save(self, fmt: str) -> None:
        """Save the selected result as ``fmt`` (docx, txt, pdf, md, html)."""
        item = self.current_item()
        if item is None or item.document is None:
            return
        if self.exporter.busy:
            self.toast.show_message(S.EXPORT_BUSY)
            return
        suggested = self._last_dir / default_output_name(item.path, fmt)
        path_str, _ = QFileDialog.getSaveFileName(
            self, S.SAVE_DIALOG_TITLE, str(suggested), S.FORMAT_FILTERS[fmt]
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != f".{fmt}":
            path = path.with_name(path.name + f".{fmt}")
        # The native dialog has already asked before overwriting.
        overwrite = path.exists()
        document = item.document
        structure = self.keep_structure_cb.isChecked()
        self._last_dir = path.parent
        if fmt == "pdf":
            options = item.options or self.options()
            source = item.path
            factory = self.controller.engine_factory

            def job(progress: Callable[[ProgressEvent], None], cancel: threading.Event) -> Path:
                engine = factory()
                assert isinstance(engine, PdfRenderer)
                return export_searchable_pdf(
                    source,
                    path,
                    engine,
                    options,
                    overwrite=overwrite,
                    on_progress=progress,
                    cancel=cancel,
                )

            self.exporter.start(item.id, job)
            if self._is_selected(item.id):
                self.result.show_progress(None, title=S.EXPORTING_TITLE)
            return
        try:
            if fmt == "txt":
                export_txt(document, path, layout=self.result.layout_mode, overwrite=overwrite)
            elif fmt == "docx":
                export_docx(document, path, structure=structure, overwrite=overwrite)
            elif fmt == "md":
                export_markdown(document, path, structure=structure, overwrite=overwrite)
            elif fmt == "html":
                export_html(
                    document, path, structure=structure, title=item.path.stem, overwrite=overwrite
                )
        except OutputExistsError:
            return
        except OSError:
            _log.error("Saving %s failed (OSError)", fmt)
            QMessageBox.warning(self, S.APP_NAME, S.SAVE_FAILED)
            return
        self._saved(path)

    def save_txt(self) -> None:
        self.save("txt")

    def _saved(self, path: Path) -> None:
        self._last_saved = path
        self.toast.show_message(S.saved_as(path.name), S.SHOW_IN_FOLDER)

    def _on_export_progress(self, item_id: int, event: ProgressEvent) -> None:
        if self._is_selected(item_id):
            self.result.show_progress(event, title=S.EXPORTING_TITLE)

    def _on_export_finished(self, item_id: int, path: Path) -> None:
        self._refresh_selected()
        self._saved(path)

    def _on_export_failed(self, item_id: int, code: str) -> None:
        self._refresh_selected()
        if code == ErrorCode.CANCELLED.value:
            self.toast.show_message(S.EXPORT_CANCELLED)
        elif code == WRITE_FAILED:
            QMessageBox.warning(self, S.APP_NAME, S.SAVE_FAILED)
        else:
            QMessageBox.warning(self, S.APP_NAME, S.error_message(ErrorCode(code)))

    def _on_copied(self) -> None:
        self.toast.show_message(S.COPIED)

    def _show_last_saved(self) -> None:
        if self._last_saved is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_saved.parent)))

    # --- header actions ------------------------------------------------------------------

    def open_settings(self) -> None:
        QMessageBox.information(self, S.SETTINGS, S.SETTINGS_SOON)

    def open_help(self) -> None:
        QMessageBox.information(self, S.HELP, S.HELP_SOON)

    # --- window-level drag & drop ----------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if accepts(dropped_paths(event)):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = dropped_paths(event)
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._sized:
            # Distribute the real width once: queue fixed, preview and result 1:1.
            self._sized = True
            total = self.splitter.width()
            left = 290
            rest = max(0, total - left - 2 * self.splitter.handleWidth())
            self.splitter.setSizes([left, rest // 2, rest - rest // 2])

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self.controller.shutdown()
        self.exporter.shutdown()
        self.preview.shutdown()
        self.queue.clear()
        tempdir.cleanup()
        super().closeEvent(event)
