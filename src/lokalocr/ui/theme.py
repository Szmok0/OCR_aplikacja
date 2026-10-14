"""Theme tokens (§7.7) and the Qt style sheet generated from them.

Colours live only here; widgets refer to them through object names and
dynamic properties in the QSS, or through :func:`color` for painting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ThemeName = Literal["light", "dark", "system"]


@dataclass(frozen=True, slots=True)
class Tokens:
    accent: str
    accent_hover: str
    accent_soft: str
    success: str
    danger: str
    danger_soft: str
    bg: str
    surface: str
    surface_alt: str
    border: str
    preview_bg: str
    text: str
    text_muted: str
    on_accent: str
    selection_text: str
    highlight: str  # search hits


LIGHT = Tokens(
    accent="#0A64F5",
    accent_hover="#0753D1",
    accent_soft="#DCECFE",
    success="#087A35",  # reference #0ABB4B is 2.6:1 on white; this passes WCAG AA as text
    danger="#C0272F",  # reference #F05058 is 3.3:1 on white; this passes WCAG AA as text
    danger_soft="#FDECEC",
    bg="#FCFCFC",
    surface="#F6F6F6",
    surface_alt="#FFFFFF",
    border="#E4EAF0",
    preview_bg="#3B3F46",
    text="#1F2937",
    text_muted="#5F6876",
    on_accent="#FFFFFF",
    selection_text="#1F2937",
    highlight="#FFE58A",
)

DARK = Tokens(
    accent="#4C8DFF",
    accent_hover="#6A9FFF",
    accent_soft="#1B2B45",
    success="#2FD36A",
    danger="#FF6B72",
    danger_soft="#3A1F22",
    bg="#16181D",
    surface="#1E2127",
    surface_alt="#23262D",
    border="#2C313A",
    preview_bg="#0F1115",
    text="#E6E8EB",
    text_muted="#9AA1AB",
    on_accent="#0B1220",
    selection_text="#E6E8EB",
    highlight="#7A5B00",
)

_current: Tokens = LIGHT


def tokens() -> Tokens:
    return _current


def color(name: str) -> QColor:
    return QColor(getattr(_current, name))


def resolve(name: ThemeName) -> Tokens:
    if name == "dark":
        return DARK
    if name == "light":
        return LIGHT
    hints = QGuiApplication.styleHints()
    return DARK if hints.colorScheme() == Qt.ColorScheme.Dark else LIGHT


def apply(app: QApplication, name: ThemeName = "system", font_pt: float | None = None) -> Tokens:
    global _current
    _current = resolve(name)
    t = _current
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(t.bg))
    palette.setColor(QPalette.ColorRole.Base, QColor(t.surface_alt))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t.surface))
    palette.setColor(QPalette.ColorRole.Text, QColor(t.text))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(t.surface_alt))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(t.on_accent))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_muted))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.surface_alt))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text))
    palette.setColor(QPalette.ColorRole.Link, QColor(t.accent))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.text_muted))
    app.setPalette(palette)
    if font_pt:
        font = app.font()
        font.setPointSizeF(font_pt)
        app.setFont(font)
    app.setStyleSheet(stylesheet(t))
    return t


def stylesheet(t: Tokens) -> str:
    return f"""
QMainWindow, QDialog {{ background: {t.bg}; }}
QWidget {{ color: {t.text}; }}
QToolTip {{ background: {t.surface_alt}; color: {t.text}; border: 1px solid {t.border};
           padding: 4px 6px; border-radius: 6px; }}

#AppHeader {{ background: {t.surface_alt}; border-bottom: 1px solid {t.border}; }}
#AppTitle {{ font-size: 15pt; font-weight: 600; }}
#AppSubtitle, .muted, QLabel[muted="true"] {{ color: {t.text_muted}; }}
QLabel[heading="true"] {{ font-weight: 600; }}
#OfflineBadge {{ color: {t.text}; }}

#Panel {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 12px; }}

#AboutTitle {{ font-size: 15pt; font-weight: 600; }}
#CreditCard {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-left: 3px solid {t.accent};
               border-radius: 10px; }}
#CreditLabel {{ letter-spacing: 0.5px; }}
#CreditName {{ font-size: 13pt; font-weight: 600; color: {t.text}; }}

#DropZone {{ background: {t.surface_alt}; border: 2px dashed {t.accent}; border-radius: 12px; }}
#DropZone[dragActive="true"] {{ background: {t.accent_soft}; }}

QPushButton {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 8px;
              padding: 6px 12px; }}
QPushButton:hover {{ border-color: {t.accent}; }}
QPushButton:focus {{ border: 2px solid {t.accent}; }}
QPushButton:disabled {{ color: {t.text_muted}; background: {t.surface}; }}
QPushButton[primary="true"] {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent};
                              font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t.accent_hover}; }}
QPushButton[primary="true"]:disabled {{ background: {t.border}; color: {t.text_muted};
                                       border-color: {t.border}; }}
QPushButton[danger="true"] {{ color: {t.danger}; border: 1px solid {t.danger}; }}
QPushButton[danger="true"]:hover {{ background: {t.danger_soft}; }}
QPushButton[link="true"] {{ border: none; background: transparent; color: {t.accent}; padding: 2px 4px; }}
QPushButton[link="true"]:hover {{ text-decoration: underline; }}
QPushButton[segment="true"] {{ border-radius: 6px; padding: 5px 10px; }}
QPushButton[segment="true"]:checked {{ background: {t.accent}; color: {t.on_accent}; border-color: {t.accent}; }}

QToolButton[primary="true"] {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent};
                               border-radius: 8px; padding: 6px 12px; font-weight: 600; }}
QToolButton[primary="true"]:hover {{ background: {t.accent_hover}; }}
QToolButton[primary="true"]:disabled {{ background: {t.border}; color: {t.text_muted}; border-color: {t.border}; }}
QToolButton[primary="true"]::menu-button {{ border-left: 1px solid {t.on_accent}; width: 22px;
                                           border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 4px; background: transparent; }}
QToolButton:hover {{ background: {t.surface}; border-color: {t.border}; }}
QToolButton:checked {{ background: {t.accent_soft}; border-color: {t.accent}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton:focus {{ border: 2px solid {t.accent}; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{ background: {t.surface_alt}; border: 1px solid {t.border};
                                     border-radius: 8px; padding: 5px 8px;
                                     selection-background-color: {t.accent};
                                     selection-color: {t.on_accent}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 2px solid {t.accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {t.surface_alt}; border: 1px solid {t.border};
                              selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}

QRadioButton::indicator, QCheckBox::indicator {{ width: 16px; height: 16px; }}
QRadioButton:disabled, QCheckBox:disabled {{ color: {t.text_muted}; }}
QLineEdit#PageSpin {{ padding: 2px 4px; }}

QProgressBar {{ background: {t.border}; border: none; border-radius: 3px; max-height: 6px;
               text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}

QTabBar::tab {{ background: transparent; border: none; padding: 8px 14px; color: {t.text_muted}; }}
QTabBar::tab:selected {{ color: {t.accent}; border-bottom: 2px solid {t.accent}; font-weight: 600; }}
QTabBar::tab:disabled {{ color: {t.border}; }}

QListView#QueueList {{ background: transparent; border: none; outline: none; }}
QSplitter::handle {{ background: transparent; }}

QMenu {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
QMenu::item:disabled {{ color: {t.text_muted}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

#Toast {{ background: {t.text}; color: {t.bg}; border-radius: 8px; padding: 8px 12px; }}
#Toast QLabel {{ color: {t.bg}; }}
#Toast QPushButton {{ color: {t.accent_soft}; background: transparent; border: none; font-weight: 600; }}
#ErrorBanner {{ background: {t.danger_soft}; border: 1px solid {t.danger}; border-radius: 8px; }}
"""
