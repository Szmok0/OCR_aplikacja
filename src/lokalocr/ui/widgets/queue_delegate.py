"""Painting of queue items (§7.3 zone 1, §7.11): thumbnail, name, size, status."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from lokalocr.ui import icons, theme
from lokalocr.ui import strings_pl as S
from lokalocr.ui.queue_model import ITEM_ROLE, QueueItem, Status

ITEM_HEIGHT = 76
THUMB_W, THUMB_H = 44, 56
MORE_SIZE = 26


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")


def details_text(item: QueueItem) -> str:
    size = human_size(item.size_bytes)
    if item.page_count is None:
        return size
    pages = S.plural_pl(item.page_count, "strona", "strony", "stron")
    return f"{item.page_count} {pages} • {size}"


def more_button_rect(option_rect: QRect) -> QRect:
    return QRect(option_rect.right() - MORE_SIZE - 8, option_rect.top() + 10, MORE_SIZE, MORE_SIZE)


class QueueDelegate(QStyledItemDelegate):
    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        return QSize(option.rect.width(), ITEM_HEIGHT)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        item: QueueItem | None = index.data(ITEM_ROLE)
        if item is None:
            return
        t = theme.tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 3, -2, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 10, 10)
        if selected:
            painter.fillPath(path, QColor(t.accent_soft))
            painter.setPen(QPen(QColor(t.accent), 1))
            painter.drawPath(path)
        elif hovered:
            painter.fillPath(path, QColor(t.surface))

        # Thumbnail
        thumb_rect = QRect(
            rect.left() + 10, rect.top() + (rect.height() - THUMB_H) // 2, THUMB_W, THUMB_H
        )
        painter.fillRect(thumb_rect, QColor(t.surface_alt))
        if item.thumbnail is not None and not item.thumbnail.isNull():
            scaled = item.thumbnail.scaled(
                thumb_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = thumb_rect.left() + (thumb_rect.width() - scaled.width()) // 2
            y = thumb_rect.top() + (thumb_rect.height() - scaled.height()) // 2
            painter.drawImage(x, y, scaled)
        else:
            kind = "file_pdf" if item.file_kind == "pdf" else "file_image"
            painter.drawPixmap(
                thumb_rect.center().x() - 11,
                thumb_rect.center().y() - 11,
                icons.pixmap(kind, 22, "text_muted"),
            )
        painter.setPen(QPen(QColor(t.border), 1))
        painter.drawRect(thumb_rect)

        # Texts
        left = thumb_rect.right() + 12
        right = rect.right() - MORE_SIZE - 14
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(t.text))
        fm = QFontMetrics(font)
        name = fm.elidedText(item.name, Qt.TextElideMode.ElideMiddle, right - left)
        painter.drawText(
            QRect(left, rect.top() + 8, right - left, 20),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            name,
        )

        small = QFont(option.font)
        small.setPointSizeF(max(7.5, option.font.pointSizeF() - 1))
        painter.setFont(small)
        painter.setPen(QColor(t.text_muted))
        painter.drawText(
            QRect(left, rect.top() + 28, right - left, 18),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            details_text(item),
        )

        status_rect = QRect(left, rect.top() + 48, rect.right() - left - 10, 18)
        self._paint_status(painter, status_rect, item, small)

        # "⋯" menu button
        more = more_button_rect(option.rect)
        if hovered or selected:
            painter.drawPixmap(
                more.center().x() - 9, more.center().y() - 9, icons.pixmap("icon_more", 18, "text")
            )
        painter.restore()

    def _paint_status(self, painter: QPainter, rect: QRect, item: QueueItem, font: QFont) -> None:
        t = theme.tokens()
        painter.setFont(font)
        align = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        icon_y = rect.top() + (rect.height() - 14) // 2
        text_rect = rect.adjusted(20, 0, 0, 0)
        if item.status is Status.DONE:
            painter.drawPixmap(rect.left(), icon_y, icons.pixmap("status_ok", 14, "success"))
            painter.setPen(QColor(t.success))
            painter.drawText(text_rect, align, S.STATUS_DONE)
        elif item.status is Status.WAITING:
            painter.drawPixmap(rect.left(), icon_y, icons.pixmap("status_wait", 14, "text_muted"))
            painter.setPen(QColor(t.text_muted))
            painter.drawText(text_rect, align, S.STATUS_WAITING)
        elif item.status is Status.ERROR:
            painter.drawPixmap(rect.left(), icon_y, icons.pixmap("status_error", 14, "danger"))
            painter.setPen(QColor(t.danger))
            fm = QFontMetrics(font)
            message = S.short_error(item.error_code)
            painter.drawText(
                text_rect,
                align,
                fm.elidedText(message, Qt.TextElideMode.ElideRight, text_rect.width()),
            )
        else:
            pct = round(item.progress)
            label = f"{S.STATUS_PROCESSING} {pct}%"
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(label) + 8
            bar = QRectF(rect.left(), rect.center().y() - 2, max(20, rect.width() - text_w - 4), 5)
            bg = QPainterPath()
            bg.addRoundedRect(bar, 2.5, 2.5)
            painter.fillPath(bg, QColor(t.border))
            fill = QRectF(bar.left(), bar.top(), bar.width() * min(1.0, item.progress / 100), 5)
            fg = QPainterPath()
            fg.addRoundedRect(fill, 2.5, 2.5)
            painter.fillPath(fg, QColor(t.accent))
            painter.setPen(QColor(t.text_muted))
            painter.drawText(
                QRect(int(bar.right()) + 8, rect.top(), text_w, rect.height()), align, label
            )
