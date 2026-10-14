"""Settings dialog (§7.5): category list + stacked pages, applied with OK / Anuluj."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lokalocr import __version__, config, tempdir
from lokalocr.config import PDF_DPI_CHOICES, Settings
from lokalocr.docs import find_doc
from lokalocr.ui import icons
from lokalocr.ui import strings_pl as S
from lokalocr.ui.widgets.basic import ToggleSwitch, muted_label

CATEGORIES = ("ocr", "processing", "output", "appearance", "advanced", "about")
CLIPBOARD_MINUTES = (1, 2, 5, 10, 15, 30, 60)
FONT_SIZES = (9, 10, 11, 12, 13, 14, 16)


def _select(combo: QComboBox, value: object) -> None:
    """Select ``value``, adding it if a hand-edited settings file holds another one."""
    index = combo.findData(value)
    if index < 0:
        combo.addItem(str(value), value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("heading", True)
    return label


def _row(*widgets: QWidget, stretch: bool = True, indent: int = 0) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(indent, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch:
        layout.addStretch()
    return w


def _toggle_row(label: str, toggle: ToggleSwitch, tip: str = "", indent: int = 0) -> QWidget:
    text = QLabel(label)
    text.setBuddy(toggle)
    toggle.setAccessibleName(label)
    if tip:
        text.setToolTip(tip)
        toggle.setToolTip(tip)
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(indent, 0, 0, 0)
    layout.addWidget(text, 1)
    layout.addWidget(toggle)
    return w


class SettingsDialog(QDialog):
    """Edits a copy of the settings; :attr:`result_settings` holds them after OK."""

    clear_temp_requested = Signal()

    def __init__(
        self,
        settings: Settings,
        *,
        engine_info: Callable[[], tuple[str, frozenset[str]] | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.SETTINGS)
        self.setModal(True)
        self.resize(820, 560)
        self._initial = settings
        self.result_settings = settings
        self._engine_info = engine_info

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        self.categories = QListWidget()
        self.categories.setObjectName("SettingsCategories")
        self.categories.setFixedWidth(200)
        self.categories.setIconSize(QSize(18, 18))
        self.pages = QStackedWidget()
        builders = {
            "ocr": self._page_ocr,
            "processing": self._page_processing,
            "output": self._page_output,
            "appearance": self._page_appearance,
            "advanced": self._page_advanced,
            "about": self._page_about,
        }
        for key in CATEGORIES:
            item = QListWidgetItem(icons.icon(f"cat_{key}"), S.SETTINGS_CATEGORIES[key])
            self.categories.addItem(item)
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 4, 8, 4)
            builders[key](layout)
            layout.addStretch()
            self.pages.addWidget(page)
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.categories.setCurrentRow(0)
        body.addWidget(self.categories)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(S.OK)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(S.CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.load(settings)

    # --- pages ---------------------------------------------------------------------

    def _page_ocr(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_heading(S.SETTINGS_OCR_TITLE))
        form = QFormLayout()
        self.lang_combo = QComboBox()
        for code in config.LANGUAGES:
            self.lang_combo.addItem(S.LANGUAGE_LABELS[code], code)
        form.addRow(S.DEFAULT_LANGUAGE, self.lang_combo)
        layout.addLayout(form)
        layout.addSpacing(12)
        layout.addWidget(_heading(S.COMPONENT_STATUS))
        self.lang_status = QLabel(S.CHECKING)
        self.lang_status.setWordWrap(True)
        status = QFormLayout()
        status.addRow(S.LANGUAGE_DATA, self.lang_status)
        layout.addLayout(status)
        self._fill_engine_status()

    def _fill_engine_status(self) -> None:
        info = self._engine_info() if self._engine_info else None
        if info is None:
            self.lang_status.setText(S.ENGINE_NOT_FOUND)
            return
        version, langs = info
        missing = {"pol", "eng"} - langs
        names = ", ".join(sorted(langs)) or "—"
        text = S.engine_status(version, names)
        if missing:
            text += "\n" + S.missing_languages(", ".join(sorted(missing)))
        self.lang_status.setText(text)

    def _page_processing(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_heading(S.SETTINGS_PROCESSING_TITLE))
        self.auto_toggle = ToggleSwitch()
        self.deskew_toggle = ToggleSwitch()
        self.denoise_toggle = ToggleSwitch()
        self.contrast_toggle = ToggleSwitch()
        layout.addWidget(_toggle_row(S.AUTO_PREPROCESS, self.auto_toggle, S.AUTO_PREPROCESS_TIP))
        self.detail_rows = [
            _toggle_row(S.DESKEW_OPTION, self.deskew_toggle, S.DESKEW_OPTION_TIP, indent=24),
            _toggle_row(S.DENOISE_OPTION, self.denoise_toggle, S.DENOISE_OPTION_TIP, indent=24),
            _toggle_row(S.CONTRAST_OPTION, self.contrast_toggle, S.CONTRAST_OPTION_TIP, indent=24),
        ]
        for row in self.detail_rows:
            layout.addWidget(row)
        self.auto_toggle.toggled.connect(self._sync_detail_rows)
        layout.addSpacing(12)
        form = QFormLayout()
        self.dpi_combo = QComboBox()
        for dpi in PDF_DPI_CHOICES:
            self.dpi_combo.addItem(f"{dpi} dpi", dpi)
        self.dpi_combo.setToolTip(S.PDF_DPI_TIP)
        form.addRow(S.PDF_DPI, self.dpi_combo)
        self.threads_combo = QComboBox()
        self.threads_combo.addItem(S.THREADS_AUTO, 0)
        for n in range(1, max(2, os.cpu_count() or 2) + 1):
            self.threads_combo.addItem(str(n), n)
        self.threads_combo.setToolTip(S.THREADS_TIP)
        form.addRow(S.THREADS, self.threads_combo)
        layout.addLayout(form)

    def _page_output(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_heading(S.SETTINGS_OUTPUT_TITLE))
        self.ask_radio = QRadioButton(S.OUTPUT_ASK)
        self.folder_radio = QRadioButton(S.OUTPUT_FOLDER)
        group = QButtonGroup(self)
        group.addButton(self.ask_radio)
        group.addButton(self.folder_radio)
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText(S.NO_FOLDER)
        self.output_btn = QPushButton(S.CHOOSE_FOLDER)
        self.output_btn.clicked.connect(self._choose_output)
        self.folder_radio.toggled.connect(self._sync_output_enabled)
        layout.addWidget(self.ask_radio)
        layout.addWidget(self.folder_radio)
        layout.addWidget(_row(self.output_edit, self.output_btn, stretch=False, indent=24))
        layout.addSpacing(8)
        form = QFormLayout()
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setToolTip(S.NAME_PATTERN_TIP)
        form.addRow(S.NAME_PATTERN, self.pattern_edit)
        self.format_combo = QComboBox()
        for fmt in ("docx", "txt", "pdf", "md", "html"):
            self.format_combo.addItem(S.FORMAT_LABELS[fmt], fmt)
        form.addRow(S.DEFAULT_FORMAT, self.format_combo)
        self.temp_edit = QLineEdit()
        self.temp_edit.setReadOnly(True)
        self.temp_edit.setPlaceholderText(str(tempdir.default_root()))
        temp_btn = QPushButton(S.CHOOSE_FOLDER)
        temp_btn.clicked.connect(self._choose_temp)
        temp_reset = QPushButton(S.RESET_DEFAULT)
        temp_reset.clicked.connect(lambda: self.temp_edit.setText(""))
        form.addRow(S.TEMP_FOLDER, _row(self.temp_edit, temp_btn, temp_reset, stretch=False))
        self.clipboard_combo = QComboBox()
        self.clipboard_combo.addItem(S.NEVER, 0)
        for minutes in CLIPBOARD_MINUTES:
            self.clipboard_combo.addItem(S.minutes(minutes), minutes)
        form.addRow(S.CLIPBOARD_CLEAR, self.clipboard_combo)
        layout.addLayout(form)
        note = muted_label(S.CLIPBOARD_NOTE, small=True)
        note.setWordWrap(True)
        layout.addWidget(note)

    def _page_appearance(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_heading(S.SETTINGS_APPEARANCE_TITLE))
        form = QFormLayout()
        self.theme_radios: dict[str, QRadioButton] = {}
        group = QButtonGroup(self)
        theme_row = QWidget()
        theme_layout = QHBoxLayout(theme_row)
        theme_layout.setContentsMargins(0, 0, 0, 0)
        for key in ("system", "light", "dark"):
            radio = QRadioButton(S.THEME_LABELS[key])
            group.addButton(radio)
            self.theme_radios[key] = radio
            theme_layout.addWidget(radio)
        theme_layout.addStretch()
        form.addRow(S.THEME, theme_row)
        self.font_combo = QComboBox()
        self.font_combo.addItem(S.SYSTEM_DEFAULT, 0.0)
        for size in FONT_SIZES:
            self.font_combo.addItem(f"{size} pt", float(size))
        form.addRow(S.FONT_SIZE, self.font_combo)
        self.ui_lang = QComboBox()
        self.ui_lang.addItem("Polski", "pl")
        self.ui_lang.setToolTip(S.UI_LANGUAGE_TIP)
        form.addRow(S.UI_LANGUAGE, self.ui_lang)
        layout.addLayout(form)

    def _page_advanced(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_heading(S.SETTINGS_ADVANCED_TITLE))
        form = QFormLayout()
        self.log_combo = QComboBox()
        for key in ("warning", "info", "debug"):
            self.log_combo.addItem(S.LOG_LEVELS[key], key)
        self.log_combo.setToolTip(S.LOG_LEVEL_TIP)
        form.addRow(S.LOG_LEVEL, self.log_combo)
        layout.addLayout(form)
        note = muted_label(S.LOG_NOTE, small=True)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addSpacing(8)
        open_logs = QPushButton(S.OPEN_LOG_FOLDER)
        open_logs.clicked.connect(self._open_logs)
        clear_temp = QPushButton(S.CLEAR_TEMP)
        clear_temp.clicked.connect(self._clear_temp)
        restore = QPushButton(S.RESTORE_DEFAULTS)
        restore.clicked.connect(self._restore_defaults)
        for button in (open_logs, clear_temp, restore):
            layout.addWidget(_row(button))

    def _page_about(self, layout: QVBoxLayout) -> None:
        # Header: app icon, name and version, subtitle.
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(QSize(56, 56)))
        logo.setFixedSize(56, 56)
        title = QLabel(f"{S.APP_NAME} {__version__}")
        title.setObjectName("AboutTitle")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addStretch()
        titles.addWidget(title)
        titles.addWidget(muted_label(S.APP_SUBTITLE))
        titles.addStretch()
        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(logo)
        header.addLayout(titles, 1)
        layout.addLayout(header)
        layout.addSpacing(6)

        # Credit card: who came up with the idea and made the application.
        credit = QFrame()
        credit.setObjectName("CreditCard")
        card = QVBoxLayout(credit)
        card.setContentsMargins(16, 10, 16, 12)
        card.setSpacing(2)
        caption = muted_label(S.CREDIT_LABEL, small=True)
        caption.setObjectName("CreditLabel")
        self.credit_name = QLabel(S.CREDIT_NAME)
        self.credit_name.setObjectName("CreditName")
        card.addWidget(caption)
        card.addWidget(self.credit_name)
        layout.addWidget(credit)
        layout.addSpacing(6)

        offline = QLabel(S.NO_NETWORK_STATEMENT)
        offline.setProperty("heading", True)
        layout.addWidget(offline)
        self.about_engine = muted_label("")
        self.about_engine.setWordWrap(True)
        layout.addWidget(self.about_engine)
        info = self._engine_info() if self._engine_info else None
        engine = info[0] if info else S.ENGINE_NOT_FOUND
        self.about_engine.setText(S.about_components(engine))
        layout.addWidget(_heading(S.LICENSES))
        browser = QTextBrowser()
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        notices = find_doc("THIRD_PARTY_NOTICES.md")
        browser.setMarkdown(notices.read_text(encoding="utf-8") if notices else S.LICENSES_MISSING)
        browser.setMinimumHeight(220)
        layout.addWidget(browser, 1)

    # --- actions --------------------------------------------------------------------

    def _sync_detail_rows(self, on: bool) -> None:
        for row in self.detail_rows:
            row.setEnabled(on)

    def _sync_output_enabled(self) -> None:
        enabled = self.folder_radio.isChecked()
        self.output_edit.setEnabled(enabled)
        self.output_btn.setEnabled(enabled)

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, S.CHOOSE_FOLDER, self.output_edit.text() or str(Path.home())
        )
        if folder:
            self.output_edit.setText(folder)
            self.folder_radio.setChecked(True)

    def _choose_temp(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, S.CHOOSE_FOLDER, self.temp_edit.text() or str(Path.home())
        )
        if folder:
            self.temp_edit.setText(folder)

    def _open_logs(self) -> None:
        folder = config.log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _clear_temp(self) -> None:
        self.clear_temp_requested.emit()
        QMessageBox.information(self, S.SETTINGS, S.TEMP_CLEARED)

    def _restore_defaults(self) -> None:
        if QMessageBox.question(self, S.SETTINGS, S.RESTORE_QUESTION) == (
            QMessageBox.StandardButton.Yes
        ):
            self.load(Settings())

    # --- data -----------------------------------------------------------------------

    def load(self, s: Settings) -> None:
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(s.default_lang)))
        self.auto_toggle.setChecked(s.auto_preprocess)
        self.deskew_toggle.setChecked(s.deskew)
        self.denoise_toggle.setChecked(s.denoise)
        self.contrast_toggle.setChecked(s.contrast)
        for row in self.detail_rows:
            row.setEnabled(s.auto_preprocess)
        self.dpi_combo.setCurrentIndex(max(0, self.dpi_combo.findData(s.pdf_dpi)))
        self.threads_combo.setCurrentIndex(max(0, self.threads_combo.findData(s.threads)))
        (self.folder_radio if s.output_dir else self.ask_radio).setChecked(True)
        self.output_edit.setText(s.output_dir)
        self._sync_output_enabled()
        self.pattern_edit.setText(s.name_pattern)
        self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(s.default_format)))
        self.temp_edit.setText(s.temp_dir)
        _select(self.clipboard_combo, s.clipboard_clear_minutes)
        self.theme_radios.get(s.theme, self.theme_radios["system"]).setChecked(True)
        _select(self.font_combo, float(s.font_size))
        self.log_combo.setCurrentIndex(max(0, self.log_combo.findData(s.log_level)))

    def collect(self) -> Settings:
        theme = next(k for k, r in self.theme_radios.items() if r.isChecked())
        pattern = self.pattern_edit.text().strip()
        return replace(
            self._initial,
            default_lang=str(self.lang_combo.currentData()),
            auto_preprocess=self.auto_toggle.isChecked(),
            deskew=self.deskew_toggle.isChecked(),
            denoise=self.denoise_toggle.isChecked(),
            contrast=self.contrast_toggle.isChecked(),
            pdf_dpi=int(self.dpi_combo.currentData()),
            threads=int(self.threads_combo.currentData()),
            output_dir=self.output_edit.text() if self.folder_radio.isChecked() else "",
            name_pattern=pattern,
            default_format=self.format_combo.currentData(),
            temp_dir=self.temp_edit.text(),
            clipboard_clear_minutes=int(self.clipboard_combo.currentData()),
            theme=theme,  # type: ignore[arg-type]
            font_size=float(self.font_combo.currentData()),
            log_level=self.log_combo.currentData(),
        ).validated()

    def accept(self) -> None:
        pattern = self.pattern_edit.text().strip()
        if config.NAME_PLACEHOLDER not in pattern:
            QMessageBox.warning(self, S.SETTINGS, S.NAME_PATTERN_INVALID)
            self.categories.setCurrentRow(CATEGORIES.index("output"))
            self.pattern_edit.setFocus()
            return
        if self.folder_radio.isChecked() and not self.output_edit.text():
            QMessageBox.warning(self, S.SETTINGS, S.OUTPUT_FOLDER_MISSING)
            self.categories.setCurrentRow(CATEGORIES.index("output"))
            return
        self.result_settings = self.collect()
        super().accept()
