"""Local help window (§6.8): renders the bundled user guide, never opens a browser."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from lokalocr.docs import find_doc
from lokalocr.ui import strings_pl as S


class HelpWindow(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.HELP_TITLE)
        self.setModal(False)
        self.resize(760, 680)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        # Links in the guide are plain text; nothing may open a browser (§6.8).
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        guide = find_doc("user-guide.md")
        self.browser.setMarkdown(
            guide.read_text(encoding="utf-8") if guide is not None else S.HELP_MISSING
        )
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(S.CLOSE)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
