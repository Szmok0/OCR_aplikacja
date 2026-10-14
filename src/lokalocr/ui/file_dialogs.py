"""File dialogs that leave no trace of document names or folders (§6.5).

* The native Windows dialog adds every opened or saved file to the system's
  "Recent items" and the dialog's own history in the registry (Qt does not set
  ``FOS_DONTADDTORECENT``). Qt's own dialog does neither, so it is used instead.
* Every ``QFileDialog`` writes the folders it visited to Qt's settings shared by
  all Qt applications (on Windows ``HKCU\\Software\\QtProject\\OrganizationDefaults\\
  FileDialog``). Those entries are put back exactly as they were before.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QWidget

__all__ = ["OPTIONS", "existing_directory", "no_history", "open_file_names", "save_file_name"]

OPTIONS = QFileDialog.Option.DontUseNativeDialog
HISTORY_KEYS = ("FileDialog/history", "FileDialog/lastVisited")


def _qt_settings() -> QSettings:
    return QSettings(QSettings.Scope.UserScope, "QtProject")


@contextmanager
def no_history() -> Iterator[None]:
    settings = _qt_settings()
    saved = {key: settings.value(key) for key in HISTORY_KEYS if settings.contains(key)}
    try:
        yield
    finally:
        # The dialog has written its own QSettings by now: start from a fresh copy.
        settings = _qt_settings()
        for key in HISTORY_KEYS:
            if key in saved:
                settings.setValue(key, saved[key])
            else:
                settings.remove(key)
        settings.sync()


def open_file_names(parent: QWidget, caption: str, directory: str, filters: str) -> list[str]:
    with no_history():
        files, _ = QFileDialog.getOpenFileNames(parent, caption, directory, filters, "", OPTIONS)
    return list(files)


def save_file_name(parent: QWidget, caption: str, suggested: str, filters: str) -> str:
    with no_history():
        path, _ = QFileDialog.getSaveFileName(parent, caption, suggested, filters, "", OPTIONS)
    return str(path)


def existing_directory(parent: QWidget, caption: str, directory: str) -> str:
    with no_history():
        folder = QFileDialog.getExistingDirectory(
            parent, caption, directory, OPTIONS | QFileDialog.Option.ShowDirsOnly
        )
    return str(folder)
