"""File queue (§7.3 zone 1): items live only in memory (§6.5)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QImage

from lokalocr.errors import ErrorCode
from lokalocr.model import Document
from lokalocr.pipeline import ProcessOptions, Stage

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1

_ids = itertools.count(1)

ModelIndex = QModelIndex | QPersistentModelIndex


class Status(StrEnum):
    WAITING = "waiting"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


@dataclass(eq=False)
class QueueItem:
    path: Path
    size_bytes: int
    id: int = field(default_factory=lambda: next(_ids))
    page_count: int | None = None
    status: Status = Status.WAITING
    progress: float = 0.0
    stage: Stage | None = None
    eta_seconds: float | None = None
    error_code: ErrorCode | None = None
    document: Document | None = None
    options: ProcessOptions | None = None  # options the current result was made with
    thumbnail: QImage | None = None
    file_kind: str = "file"  # pdf | image
    paused: bool = False  # cancelled by the user; skipped until reprocessed

    @property
    def name(self) -> str:
        return self.path.name


class QueueModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self._items: list[QueueItem] = []

    # --- Qt model API -----------------------------------------------------------

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == ITEM_ROLE:
            return item
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.name
        return None

    # --- queue API ----------------------------------------------------------------

    def items(self) -> list[QueueItem]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def add(self, item: QueueItem) -> QueueItem:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()
        return item

    def get(self, item_id: int) -> QueueItem | None:
        return next((i for i in self._items if i.id == item_id), None)

    def row_of(self, item_id: int) -> int:
        return next((r for r, i in enumerate(self._items) if i.id == item_id), -1)

    def contains_path(self, path: Path) -> bool:
        return self.find_path(path) is not None

    def find_path(self, path: Path) -> QueueItem | None:
        resolved = path.resolve()
        return next((i for i in self._items if i.path.resolve() == resolved), None)

    def changed(self, item_id: int) -> None:
        row = self.row_of(item_id)
        if row >= 0:
            idx = self.index(row)
            self.dataChanged.emit(idx, idx)

    def remove(self, item_id: int) -> None:
        row = self.row_of(item_id)
        if row < 0:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        item = self._items.pop(row)
        self.endRemoveRows()
        item.document = None
        item.thumbnail = None

    def clear(self) -> None:
        self.beginResetModel()
        for item in self._items:
            item.document = None
            item.thumbnail = None
        self._items.clear()
        self.endResetModel()

    def processing(self) -> QueueItem | None:
        return next((i for i in self._items if i.status is Status.PROCESSING), None)
