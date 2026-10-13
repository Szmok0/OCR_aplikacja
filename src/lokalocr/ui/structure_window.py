"""Non-modal "Struktura dokumentu" window (§7.4), read-only in v1.

Left: tree Page -> headings, sections and grouped blocks. Middle: crop of the
selected block (or the figure image). Right: block properties. Selecting a
block asks the main window to show and highlight it in the page preview.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lokalocr.model import Block, BlockType, Document, Page, block_text
from lokalocr.ui import icons
from lokalocr.ui import strings_pl as S
from lokalocr.ui.widgets.basic import ToggleSwitch, muted_label

BLOCK_ROLE = Qt.ItemDataRole.UserRole + 1
PAGE_ROLE = Qt.ItemDataRole.UserRole + 2

NODE_ICONS = {
    BlockType.HEADING: "node_heading",
    BlockType.PARAGRAPH: "node_paragraph",
    BlockType.LIST_ITEM: "node_list",
    BlockType.TABLE: "node_table",
    BlockType.FIGURE: "node_image",
    BlockType.CAPTION: "node_paragraph",
}


def _short(text: str, limit: int = 48) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class StructureWindow(QDialog):
    block_selected = Signal(int, object)  # page index (0-based), Block
    highlight_toggled = Signal(bool)

    def __init__(
        self,
        document: Document,
        source: Path,
        page_image: Callable[[int], QImage | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle(S.structure_title(source.name))
        self.resize(1080, 640)
        self._document = document
        self._page_image = page_image

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName(S.STRUCTURE_TREE)
        self.tree.currentItemChanged.connect(self._on_current)
        splitter.addWidget(self.tree)

        preview_panel = QFrame()
        preview_panel.setObjectName("Panel")
        pv = QVBoxLayout(preview_panel)
        title = QLabel(S.BLOCK_PREVIEW)
        title.setProperty("heading", True)
        pv.addWidget(title)
        self.preview = QLabel(S.SELECT_BLOCK)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(260, 260)
        self.preview.setWordWrap(True)
        pv.addWidget(self.preview, 1)
        splitter.addWidget(preview_panel)

        props_panel = QFrame()
        props_panel.setObjectName("Panel")
        pp = QVBoxLayout(props_panel)
        ptitle = QLabel(S.BLOCK_PROPERTIES)
        ptitle.setProperty("heading", True)
        pp.addWidget(ptitle)
        pp.addWidget(muted_label(S.READ_ONLY_NOTE, small=True))
        form = QFormLayout()
        self.type_label = QLabel("—")
        self.level_label = QLabel("—")
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setMaximumHeight(120)
        self.coords_label = QLabel("—")
        form.addRow(S.BLOCK_TYPE, self.type_label)
        form.addRow(S.BLOCK_TEXT, self.text_view)
        form.addRow(S.BLOCK_LEVEL, self.level_label)
        form.addRow(S.BLOCK_COORDS, self.coords_label)
        pp.addLayout(form)
        toggle_row = QHBoxLayout()
        self.frame_toggle = ToggleSwitch()
        self.frame_toggle.setChecked(True)
        self.frame_toggle.setAccessibleName(S.SHOW_BLOCK_FRAME)
        self.frame_toggle.toggled.connect(self.highlight_toggled)
        toggle_row.addWidget(QLabel(S.SHOW_BLOCK_FRAME), 1)
        toggle_row.addWidget(self.frame_toggle)
        pp.addLayout(toggle_row)
        pp.addWidget(QLabel(S.CONFIDENCE))
        conf_row = QHBoxLayout()
        self.conf_bar = QProgressBar()
        self.conf_bar.setRange(0, 100)
        self.conf_bar.setTextVisible(False)
        self.conf_label = QLabel("—")
        conf_row.addWidget(self.conf_bar, 1)
        conf_row.addWidget(self.conf_label)
        pp.addLayout(conf_row)
        pp.addStretch()
        splitter.addWidget(props_panel)
        splitter.setSizes([340, 400, 340])

        self._fill_tree()

    # --- tree ------------------------------------------------------------------------

    def _block_item(self, block: Block, page_index: int) -> QTreeWidgetItem:
        label = S.BLOCK_TYPE_LABELS[block.type.value]
        text = block_text(block) if block.type is not BlockType.FIGURE else ""
        item = QTreeWidgetItem([f"{label}: {_short(text)}" if text else label])
        item.setIcon(0, icons.icon(NODE_ICONS[block.type]))
        item.setData(0, BLOCK_ROLE, block)
        item.setData(0, PAGE_ROLE, page_index)
        return item

    def _add_blocks(self, parent: QTreeWidgetItem, blocks: list[Block], page_index: int) -> None:
        """Group runs of paragraphs / list items: "Akapit (2)", "Lista (4)"."""
        i = 0
        while i < len(blocks):
            block = blocks[i]
            j = i
            while (
                block.type in (BlockType.PARAGRAPH, BlockType.LIST_ITEM)
                and j + 1 < len(blocks)
                and blocks[j + 1].type is block.type
            ):
                j += 1
            run = blocks[i : j + 1]
            if len(run) > 1:
                group_label = S.GROUP_LABELS[block.type.value]
                group = QTreeWidgetItem([f"{group_label} ({len(run)})"])
                group.setIcon(0, icons.icon(NODE_ICONS[block.type]))
                for b in run:
                    group.addChild(self._block_item(b, page_index))
                parent.addChild(group)
            else:
                parent.addChild(self._block_item(block, page_index))
            i = j + 1

    def _fill_page(self, node: QTreeWidgetItem, page: Page, page_index: int) -> None:
        stack: list[tuple[int, QTreeWidgetItem]] = []
        pending: list[Block] = []

        def flush() -> None:
            target = stack[-1][1] if stack else node
            self._add_blocks(target, pending, page_index)
            pending.clear()

        for block in page.blocks:
            if block.type is BlockType.HEADING:
                flush()
                level = block.level or 1
                while stack and stack[-1][0] >= level:
                    stack.pop()
                section = QTreeWidgetItem([S.section_label(_short(block.text, 40))])
                section.setIcon(0, icons.icon("node_section"))
                section.addChild(self._block_item(block, page_index))
                (stack[-1][1] if stack else node).addChild(section)
                stack.append((level, section))
            else:
                pending.append(block)
        flush()

    def _fill_tree(self) -> None:
        self.tree.clear()
        for index, page in enumerate(self._document.pages):
            node = QTreeWidgetItem([S.page_label(page.number)])
            node.setIcon(0, icons.icon("node_page"))
            self.tree.addTopLevelItem(node)
            self._fill_page(node, page, index)
            node.setExpanded(True)
        self.tree.expandToDepth(1)

    # --- selection -------------------------------------------------------------------------

    def _on_current(self, current: QTreeWidgetItem | None, _prev: object) -> None:
        block = current.data(0, BLOCK_ROLE) if current is not None else None
        if not isinstance(block, Block):
            return
        page_index = int(current.data(0, PAGE_ROLE)) if current is not None else 0
        self.show_block(block, page_index)
        self.block_selected.emit(page_index, block)

    def show_block(self, block: Block, page_index: int) -> None:
        self.type_label.setText(S.BLOCK_TYPE_LABELS[block.type.value])
        self.level_label.setText(f"H{block.level}" if block.level else "—")
        self.text_view.setPlainText(block_text(block))
        if block.bbox is not None:
            b = block.bbox
            self.coords_label.setText(S.coords(b.x, b.y, b.width, b.height))
        else:
            self.coords_label.setText("—")
        if block.confidence is None:
            self.conf_bar.setValue(0)
            self.conf_label.setText("—")
        else:
            pct = round(block.confidence * 100)
            self.conf_bar.setValue(pct)
            self.conf_label.setText(f"{pct}%")
        self._show_preview(block, page_index)

    def _show_preview(self, block: Block, page_index: int) -> None:
        image: QImage | None = None
        if block.type is BlockType.FIGURE and block.image_ref in self._document.images:
            image = QImage.fromData(self._document.images[block.image_ref or ""])
        elif block.bbox is not None and page_index < len(self._document.pages):
            page_img = self._page_image(page_index)
            page = self._document.pages[page_index]
            if page_img is not None and not page_img.isNull():
                sx = page_img.width() / max(1, page.width)
                sy = page_img.height() / max(1, page.height)
                b = block.bbox
                pad = 6
                image = page_img.copy(
                    max(0, round(b.x * sx) - pad), max(0, round(b.y * sy) - pad),
                    round(b.width * sx) + 2 * pad, round(b.height * sy) + 2 * pad,
                )  # fmt: skip
        if image is None or image.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(S.NO_BLOCK_PREVIEW)
            return
        pixmap = QPixmap.fromImage(image).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )  # fmt: skip
        self.preview.setPixmap(pixmap)

    @property
    def highlight_enabled(self) -> bool:
        return self.frame_toggle.isChecked()
