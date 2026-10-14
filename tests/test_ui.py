"""Main window tests (stage 3), run offscreen with a controllable fake engine."""

from __future__ import annotations

import io
import shutil
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox
from pytestqt.qtbot import QtBot

from lokalocr import tempdir
from lokalocr.errors import CancelledError, ErrorCode
from lokalocr.model import BBox, Block, BlockType, Line, Page
from lokalocr.ui import strings_pl as S
from lokalocr.ui import theme
from lokalocr.ui.app import create_app
from lokalocr.ui.main_window import MainWindow
from lokalocr.ui.queue_model import Status


class FakeEngine:
    """Returns fixed text; can be slowed down or blocked until cancelled."""

    name = "fake"

    def __init__(self, delay: float = 0.0, block: bool = False) -> None:
        self.delay = delay
        self.block = block
        self.calls = 0

    def recognize(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        page_number: int = 1,
        cancel: threading.Event | None = None,
    ) -> Page:
        self.calls += 1
        deadline = time.monotonic() + (60 if self.block else self.delay)
        while time.monotonic() < deadline:
            if cancel is not None and cancel.wait(0.01):
                raise CancelledError("cancelled")
        lines = [
            Line("Zażółć gęślą jaźń — księgowa", BBox(10, 10, 280, 20), 0.97),
            Line(f"Strona {page_number}", BBox(10, 40, 80, 20), 0.91),
        ]
        return Page(
            page_number,
            image.width,
            image.height,
            dpi,
            [
                Block(
                    BlockType.PARAGRAPH,
                    "\n".join(ln.text for ln in lines),
                    lines,
                    BBox(10, 10, 280, 50),
                    0.94,
                )
            ],
        )

    def searchable_pdf(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        cancel: threading.Event | None = None,
        jpeg_quality: int | None = 80,
    ) -> bytes:
        self.recognize(image, lang, dpi=dpi, cancel=cancel)
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "PDF", resolution=float(dpi))
        return buf.getvalue()

    def available_languages(self) -> frozenset[str]:
        return frozenset({"pol", "eng"})

    def version(self) -> str:
        return "fake"


@pytest.fixture
def files(tmp_path: Path, fixtures_dir: Path) -> Path:
    for name in ("cv.png", "contract.pdf", "invoice.png"):
        shutil.copy(fixtures_dir / name, tmp_path / name)
    return tmp_path


def make_window(qtbot: QtBot, engine: FakeEngine) -> MainWindow:
    create_app(["test"])
    window = MainWindow(lambda: engine)
    qtbot.addWidget(window)
    window.show()
    return window


def wait_idle(qtbot: QtBot, window: MainWindow, timeout: int = 15000) -> None:
    qtbot.waitUntil(
        lambda: (
            not window.controller.busy
            and all(
                i.status in (Status.DONE, Status.ERROR) or i.paused for i in window.queue.items()
            )
        ),
        timeout=timeout,
    )


def test_starts_without_dialogs(qtbot: QtBot) -> None:
    window = make_window(qtbot, FakeEngine())
    assert QApplication.activeModalWidget() is None
    assert window.offline_badge.label.text() == S.OFFLINE_BADGE
    assert window.queue_title.text() == "Kolejka plików (0)"
    assert not window.save_main_btn.isEnabled()
    assert window.result.empty_title.text() == S.EMPTY_RESULT_TITLE


def test_garbage_is_collected_only_in_gui_thread(qtbot: QtBot) -> None:
    import gc
    import weakref

    create_app(["test"])
    assert not gc.isenabled()  # worker threads never trigger a collection

    class Node:
        self_ref: object = None

    node = Node()
    node.self_ref = node  # a reference cycle: only the cyclic collector frees it
    ref = weakref.ref(node)
    del node
    junk: list[list[int]] = [[] for _ in range(gc.get_threshold()[0] + 1)]  # trips the threshold
    qtbot.waitUntil(lambda: ref() is None, timeout=5000)  # collected by the GUI timer
    del junk


def test_queue_processes_files_sequentially(qtbot: QtBot, files: Path) -> None:
    engine = FakeEngine(delay=0.05)
    window = make_window(qtbot, engine)
    window.add_paths([files])
    assert window.queue_title.text() == "Kolejka plików (3)"
    wait_idle(qtbot, window)
    items = window.queue.items()
    assert [i.status for i in items] == [Status.DONE] * 3
    pdf = next(i for i in items if i.name == "contract.pdf")
    assert pdf.page_count == 2
    qtbot.waitUntil(lambda: all(i.thumbnail is not None for i in items), timeout=5000)

    window.select_item(pdf.id)
    assert "Strona 2" in window.result.visible_text()
    status = window.result.status.text()
    assert "Stron: 2" in status and "Pewność OCR: 94%" in status
    assert "Język OCR: polski + angielski" in status
    assert window.save_main_btn.isEnabled()


def test_layout_switch_and_search(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.result.set_layout("simplified")
    assert window.result.layout_mode == "simplified"
    window.result.search.setText("gęślą")
    assert window.result.status.text() == "Wynik 1 z 1"
    assert window.result.text.textCursor().selectedText() == "gęślą"
    window.result.search.setText("nie ma")
    assert window.result.status.text() == S.SEARCH_NO_HITS


def test_copy_text(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.result.copy_text()
    assert "Zażółć gęślą jaźń" in QApplication.clipboard().text()


def test_ui_stays_responsive_during_processing(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine(delay=0.4))
    window.add_paths([files / "contract.pdf"])
    started = time.monotonic()
    ticks = 0
    while time.monotonic() - started < 0.6:
        QApplication.processEvents()
        ticks += 1
        time.sleep(0.01)
    assert window.controller.busy
    assert ticks > 30  # the event loop keeps running while OCR works
    item = window.queue.items()[0]
    assert item.status is Status.PROCESSING
    assert window.result.stack.currentIndex() == window.result.PAGE_PROGRESS
    wait_idle(qtbot, window)


def test_cancel_keeps_item_waiting(qtbot: QtBot, files: Path) -> None:
    engine = FakeEngine(block=True)
    window = make_window(qtbot, engine)
    window.add_paths([files / "cv.png"])
    qtbot.waitUntil(lambda: window.controller.busy, timeout=5000)
    item = window.queue.items()[0]
    window.cancel_item(item.id, remove=False)
    qtbot.waitUntil(lambda: item.paused, timeout=5000)
    assert item.status is Status.WAITING
    engine.block = False
    window.reprocess(item.id)
    wait_idle(qtbot, window)
    assert window.queue.items()[0].status is Status.DONE


def test_cancel_and_remove(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine(block=True))
    window.add_paths([files / "cv.png", files / "invoice.png"])
    qtbot.waitUntil(lambda: window.controller.busy, timeout=5000)
    first = window.queue.items()[0]
    window.cancel_item(first.id, remove=True)
    qtbot.waitUntil(lambda: window.queue.get(first.id) is None, timeout=5000)
    # The next file starts automatically.
    qtbot.waitUntil(lambda: window.queue.items()[0].status is Status.PROCESSING, timeout=5000)
    window.controller.cancel()


def test_cancel_dialog_offers_keep_and_remove(
    qtbot: QtBot, files: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = make_window(qtbot, FakeEngine(block=True))
    window.add_paths([files / "cv.png"])
    qtbot.waitUntil(lambda: window.controller.busy, timeout=5000)
    seen: list[str] = []

    def fake_exec(box: QMessageBox) -> int:
        seen.extend(b.text() for b in box.buttons())
        for b in box.buttons():
            if b.text() == S.CANCEL_KEEP:
                b.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    window.cancel_current()
    assert set(seen) == {S.CANCEL_KEEP, S.CANCEL_REMOVE, S.CANCEL_CONTINUE}
    qtbot.waitUntil(lambda: window.queue.items()[0].paused, timeout=5000)


def test_corrupt_and_unsupported_files(qtbot: QtBot, tmp_path: Path) -> None:
    (tmp_path / "zepsuty.pdf").write_bytes(b"%PDF-1.7 broken")
    (tmp_path / "notatka.png").write_bytes(b"to nie jest obraz")
    window = make_window(qtbot, FakeEngine())
    window.add_paths([tmp_path / "zepsuty.pdf", tmp_path / "notatka.png"])
    assert len(window.queue) == 1  # unsupported content is rejected up front
    assert window.toast.isVisible()
    wait_idle(qtbot, window)
    item = window.queue.items()[0]
    assert item.status is Status.ERROR and item.error_code is ErrorCode.CORRUPT_FILE
    window.select_item(item.id)
    assert window.result.error_text.text() == S.error_message(ErrorCode.CORRUPT_FILE)


def test_duplicates_are_ignored(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    window.add_paths([files / "cv.png"])
    assert len(window.queue) == 1


def test_new_file_is_selected_and_shown(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.add_paths([files / "invoice.png"])
    current = window.current_item()
    assert current is not None and current.path.name == "invoice.png"


def test_readding_a_file_reprocesses_it_with_changed_settings(qtbot: QtBot, files: Path) -> None:
    engine = FakeEngine()
    window = make_window(qtbot, engine)
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.add_paths([files / "invoice.png"])
    wait_idle(qtbot, window)
    calls = engine.calls
    # Same settings: nothing to redo, the file is just shown again.
    window.add_paths([files / "cv.png"])
    assert window.current_item().path.name == "cv.png"  # type: ignore[union-attr]
    assert window.toast.text.text() == S.ALREADY_IN_QUEUE
    wait_idle(qtbot, window)
    assert engine.calls == calls
    # Changed language: the user expects the new settings to apply.
    window.lang_combo.setCurrentIndex(
        (window.lang_combo.currentIndex() + 1) % window.lang_combo.count()
    )
    window.add_paths([files / "cv.png"])
    assert window.toast.text.text() == S.REPROCESSING_WITH_NEW_SETTINGS
    wait_idle(qtbot, window)
    assert engine.calls > calls
    assert len(window.queue) == 2


def test_save_txt(
    qtbot: QtBot,
    files: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path_factory.mktemp("out")
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    suggested: list[str] = []

    def fake_dialog(*args: object, **_k: object) -> tuple[str, str]:
        suggested.append(str(args[2]))
        return str(out_dir / "wynik"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_dialog)
    window.save_txt()
    assert suggested[0].endswith("cv_ocr.txt")
    saved = out_dir / "wynik.txt"
    assert "Zażółć gęślą jaźń" in saved.read_text(encoding="utf-8")
    assert window.toast.isVisible()


def test_close_leaves_no_temp_files(qtbot: QtBot, files: Path, tmp_path: Path) -> None:
    root = tmp_path / "lokalocr-temp"
    tempdir.set_root(root)
    try:
        window = make_window(qtbot, FakeEngine())
        window.add_paths([files / "cv.png"])
        wait_idle(qtbot, window)
        (tempdir.app_temp_dir() / "spill.bin").write_bytes(b"x")
        window.close()
        assert not root.exists() or not any(root.iterdir())
        assert len(window.queue) == 0
    finally:
        tempdir.set_root(None)


def test_clear_queue(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files])
    wait_idle(qtbot, window)
    window.clear_queue()
    assert len(window.queue) == 0
    assert window.queue_title.text() == "Kolejka plików (0)"
    assert window.result.stack.currentIndex() == window.result.PAGE_EMPTY


@pytest.mark.parametrize("name", ["light", "dark"])
def test_themes_apply(qtbot: QtBot, name: theme.ThemeName) -> None:
    window = make_window(qtbot, FakeEngine())
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    tokens = theme.apply(app, name)
    assert window.palette().window().color().name().upper() == tokens.bg.upper()
    theme.apply(app, "light")


# --- stage 4: tabs, preview, export ------------------------------------------------


def test_preview_shows_pages_and_navigates(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "contract.pdf"])
    wait_idle(qtbot, window)
    preview = window.preview
    qtbot.waitUntil(lambda: preview._pixmap_item is not None, timeout=5000)
    assert preview.page_total.text() == "/ 2"
    assert not preview.prev_btn.isEnabled() and preview.next_btn.isEnabled()
    preview.next_page()
    assert preview.index == 1
    qtbot.waitUntil(lambda: (files / "contract.pdf", 1) in preview._cache, timeout=5000)
    zoom = preview.view.zoom
    preview.view.zoom_in()
    assert preview.view.zoom > zoom
    assert preview.zoom_label.text() == f"{round(preview.view.zoom * 100)}%"
    preview.rotate(90)
    assert preview.view.rotation == 90


def _drag_select(
    qtbot: QtBot, window: MainWindow, x0: float, y0: float, x1: float, y1: float
) -> None:
    """Drag a selection between two points given in page (scene) coordinates."""
    from PySide6.QtCore import QPointF
    from PySide6.QtTest import QTest

    view = window.preview.view
    viewport = view.viewport()
    start = view.mapFromScene(QPointF(x0, y0))
    end = view.mapFromScene(QPointF(x1, y1))
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(viewport, end)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def _selection_menu(window: MainWindow) -> QMenu:
    """The action menu shown after a selection (opened again as on right-click)."""
    preview = window.preview
    for old in preview.findChildren(QMenu):
        old.close()
        old.deleteLater()
    QApplication.processEvents()
    preview.view.selection_finished.emit(preview.view.mapToGlobal(preview.view.rect().center()))
    menus = [m for m in preview.findChildren(QMenu) if m.isVisible()]
    assert len(menus) == 1
    return menus[0]


def _menu_action(menu: QMenu, text: str) -> QAction:
    return next(a for a in menu.actions() if a.text() == text)


def test_select_area_copy_and_save(
    qtbot: QtBot,
    files: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    preview = window.preview
    qtbot.waitUntil(lambda: preview._pixmap_item is not None, timeout=5000)
    preview.view.fit()
    preview.select_btn.setChecked(True)
    assert preview.view.select_mode and not preview.view.magnifier

    bounds = preview.view.bounds
    _drag_select(
        qtbot,
        window,
        0.25 * bounds.width(),
        0.1 * bounds.height(),
        0.75 * bounds.width(),
        0.3 * bounds.height(),
    )
    rect = preview.view.selection_rect()
    assert rect is not None
    assert rect.width() == pytest.approx(0.5 * bounds.width(), rel=0.05)
    # The window refreshes the selected item on queue updates; that must not
    # drop the selection the user has just made.
    window._refresh_selected()
    assert preview.view.selection_rect() == rect

    # The cut is taken from the full-resolution page, not from the preview.
    with Image.open(files / "cv.png") as original:
        full_w, full_h = original.size
    image = preview.selection_image()
    assert image is not None
    assert image.width() == pytest.approx(0.5 * full_w, rel=0.05)
    assert image.height() == pytest.approx(0.2 * full_h, rel=0.05)

    # Use the menu that pops up after the drag, as the user does.
    menu = _selection_menu(window)
    QApplication.clipboard().clear()
    _menu_action(menu, S.SELECTION_COPY).trigger()
    assert QApplication.clipboard().image().width() == image.width()

    out = tmp_path_factory.mktemp("cut")
    _save_to(monkeypatch, out / "zdjecie")
    _menu_action(_selection_menu(window), S.SELECTION_SAVE).trigger()
    with Image.open(out / "zdjecie.png") as saved:
        assert saved.size == (image.width(), image.height())
    _save_to(monkeypatch, out / "zdjecie.jpg")
    window.save_selection()
    with Image.open(out / "zdjecie.jpg") as saved:
        assert saved.format == "JPEG"


def test_selection_tool_edge_cases(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "contract.pdf"])
    wait_idle(qtbot, window)
    preview = window.preview
    qtbot.waitUntil(lambda: preview._pixmap_item is not None, timeout=5000)
    preview.select_btn.setChecked(True)
    # A click without dragging leaves no selection.
    _drag_select(qtbot, window, 100, 100, 101, 101)
    assert preview.view.selection_rect() is None
    # Dragging beyond the page is clamped to the page.
    bounds = preview.view.bounds
    _drag_select(qtbot, window, 50, 50, bounds.width() + 500, bounds.height() + 500)
    rect = preview.view.selection_rect()
    assert rect is not None and rect.right() <= bounds.right()
    # A 90 degree rotation of the preview is applied to the cut.
    preview.rotate(90)
    image = preview.selection_image()
    assert (
        image is not None and image.height() > image.width() * (rect.width() / rect.height()) * 0.9
    )
    # Another page or another tool drops the selection.
    preview.next_page()
    qtbot.waitUntil(lambda: (files / "contract.pdf", 1) in preview._cache, timeout=5000)
    assert preview.view.selection_rect() is None
    _drag_select(qtbot, window, 50, 50, 300, 300)
    assert preview.view.selection_rect() is not None
    preview.hand_btn.setChecked(True)
    assert not preview.select_btn.isChecked()
    assert preview.view.selection_rect() is None
    assert window.preview.selection_image() is None


def test_tabs_switch_workspace(qtbot: QtBot, files: Path) -> None:
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.tabs.setCurrentIndex(1)
    assert window.result.isHidden()
    qtbot.waitUntil(lambda: bool(window.preview._overlay_items), timeout=5000)
    window.tabs.setCurrentIndex(0)
    assert not window.result.isHidden()
    assert not window.preview._overlay_items


def _save_to(monkeypatch: pytest.MonkeyPatch, target: Path) -> list[str]:
    filters: list[str] = []

    def fake_dialog(*args: object, **_k: object) -> tuple[str, str]:
        filters.append(str(args[3]))
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_dialog)
    return filters


@pytest.mark.parametrize("fmt", ["docx", "md", "html", "txt"])
def test_save_formats(
    qtbot: QtBot,
    files: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    fmt: str,
) -> None:
    out = tmp_path_factory.mktemp("out") / "wynik"
    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    _save_to(monkeypatch, out)
    window.save(fmt)
    saved = out.with_name(f"wynik.{fmt}")
    assert saved.exists() and saved.stat().st_size > 0
    if fmt != "docx":
        assert "Zażółć gęślą jaźń" in saved.read_text(encoding="utf-8")


def test_save_pdf_in_background(
    qtbot: QtBot,
    files: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path_factory.mktemp("out") / "umowa_ocr.pdf"
    engine = FakeEngine(delay=0.2)
    window = make_window(qtbot, engine)
    window.add_paths([files / "contract.pdf"])
    wait_idle(qtbot, window)
    _save_to(monkeypatch, out)
    window.save("pdf")
    assert window.exporter.busy
    assert window.result.progress_title.text() == S.EXPORTING_TITLE
    qtbot.waitUntil(lambda: not window.exporter.busy, timeout=10000)
    qtbot.waitUntil(lambda: out.exists(), timeout=5000)
    assert out.read_bytes().startswith(b"%PDF")
    # The worker clears ``busy`` before its "finished" signal reaches the UI thread.
    qtbot.waitUntil(
        lambda: window.result.stack.currentIndex() == window.result.PAGE_RESULT, timeout=5000
    )


def test_cancel_pdf_export(
    qtbot: QtBot,
    files: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path_factory.mktemp("out") / "x.pdf"
    engine = FakeEngine()
    window = make_window(qtbot, engine)
    window.add_paths([files / "contract.pdf"])
    wait_idle(qtbot, window)
    engine.block = True
    _save_to(monkeypatch, out)
    window.save("pdf")
    window.cancel_current()  # Esc while exporting cancels the export
    qtbot.waitUntil(lambda: not window.exporter.busy, timeout=5000)
    assert not out.exists()


# --- stage 5: settings, help, clipboard, themes ---------------------------------------


def test_settings_dialog_roundtrip(qtbot: QtBot, tmp_path: Path) -> None:
    from lokalocr.config import Settings
    from lokalocr.ui.settings_dialog import CATEGORIES, SettingsDialog

    original = Settings(
        default_lang="pol",
        pdf_dpi=200,
        theme="dark",
        output_dir=str(tmp_path),
        clipboard_clear_minutes=5,
    )
    dialog = SettingsDialog(
        original, engine_info=lambda: ("tesseract 5.3.4", frozenset({"pol", "eng"}))
    )
    qtbot.addWidget(dialog)
    assert dialog.categories.count() == len(CATEGORIES)
    assert dialog.collect() == original.validated()
    assert "tesseract 5.3.4" in dialog.lang_status.text()
    dialog.dpi_combo.setCurrentIndex(dialog.dpi_combo.findData(400))
    dialog.theme_radios["light"].setChecked(True)
    dialog.pattern_edit.setText("skan_{nazwa}")
    dialog.accept()
    assert dialog.result_settings.pdf_dpi == 400
    assert dialog.result_settings.theme == "light"
    assert dialog.result_settings.name_pattern == "skan_{nazwa}"


def test_settings_dialog_rejects_bad_pattern(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from lokalocr.config import Settings
    from lokalocr.ui.settings_dialog import SettingsDialog

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dialog = SettingsDialog(Settings())
    qtbot.addWidget(dialog)
    dialog.pattern_edit.setText("bez_nazwy")
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.result_settings == Settings()


def test_about_page_is_local_and_offline(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QTextBrowser

    from lokalocr.config import Settings
    from lokalocr.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(Settings())
    qtbot.addWidget(dialog)
    browser = dialog.findChild(QTextBrowser)
    assert browser is not None
    assert not browser.openLinks() and not browser.openExternalLinks()
    assert "Lucide" in browser.toPlainText()
    assert dialog.credit_name.text() == "Jacek J."


def test_help_window_shows_local_guide(qtbot: QtBot) -> None:
    window = make_window(qtbot, FakeEngine())
    window.open_help()
    assert window._help is not None and window._help.isVisible()
    browser = window._help.browser
    assert not browser.openLinks() and not browser.openExternalLinks()
    assert "Szybki start" in browser.toPlainText()


def test_apply_settings_updates_window(qtbot: QtBot, tmp_path: Path) -> None:
    from lokalocr.config import Settings

    window = make_window(qtbot, FakeEngine())
    window.apply_settings(
        Settings(
            default_lang="eng",
            default_format="md",
            theme="dark",
            auto_preprocess=False,
            temp_dir=str(tmp_path / "tmp"),
        )
    )
    assert window.lang_combo.currentData() == "eng"
    assert window.save_main_btn.text() == "Zapisz jako Markdown"
    assert not window.preprocess_toggle.isChecked()
    assert window.options().preprocess.enabled is False
    assert tempdir.app_temp_dir() == tmp_path / "tmp"
    assert theme.tokens() is theme.DARK
    window.apply_settings(Settings())
    assert theme.tokens() is not theme.DARK or theme.resolve("system") is theme.DARK


def test_save_to_output_folder_without_dialog(
    qtbot: QtBot,
    files: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lokalocr.config import Settings

    out = tmp_path_factory.mktemp("out")
    window = make_window(qtbot, FakeEngine())
    window.apply_settings(Settings(output_dir=str(out), name_pattern="ocr_{nazwa}"))
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)

    def no_dialog(*_a: object, **_k: object) -> tuple[str, str]:
        raise AssertionError("save dialog must not open")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", no_dialog)
    window.save("txt")
    assert (out / "ocr_cv.txt").exists()
    # Existing file: asks first; "No" keeps the old file.
    (out / "ocr_cv.txt").write_text("stare", encoding="utf-8")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.save("txt")
    assert (out / "ocr_cv.txt").read_text(encoding="utf-8") == "stare"


def test_clipboard_cleared_after_timeout(qtbot: QtBot, files: Path) -> None:
    from lokalocr.config import Settings

    window = make_window(qtbot, FakeEngine())
    window.apply_settings(Settings(clipboard_clear_minutes=1))
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.result.copy_text()
    assert "Zażółć" in QApplication.clipboard().text()
    assert window._clipboard_timer.isActive()
    window._clear_clipboard()  # what the timer does after the delay
    assert QApplication.clipboard().text() == ""


def test_clipboard_not_cleared_if_user_copied_something_else(qtbot: QtBot, files: Path) -> None:
    from lokalocr.config import Settings

    window = make_window(qtbot, FakeEngine())
    window.apply_settings(Settings(clipboard_clear_minutes=1))
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    window.result.copy_text()
    QApplication.clipboard().setText("coś innego")
    window._clear_clipboard()
    assert QApplication.clipboard().text() == "coś innego"


def test_ctrl_c_without_selection_copies_all(qtbot: QtBot, files: Path) -> None:
    from PySide6.QtCore import Qt as QtCore_Qt

    window = make_window(qtbot, FakeEngine())
    window.add_paths([files / "cv.png"])
    wait_idle(qtbot, window)
    QApplication.clipboard().clear()
    window.result.text.setFocus()
    qtbot.keyClick(  # type: ignore[no-untyped-call]
        window.result.text, QtCore_Qt.Key.Key_C, QtCore_Qt.KeyboardModifier.ControlModifier
    )
    assert "Zażółć gęślą jaźń" in QApplication.clipboard().text()


def test_engine_banner(qtbot: QtBot) -> None:
    from lokalocr.errors import EngineMissingError

    def missing() -> FakeEngine:
        raise EngineMissingError("no tesseract")

    create_app(["test"])
    window = MainWindow(missing)
    qtbot.addWidget(window)
    window.show()
    window.check_engine()
    qtbot.waitUntil(lambda: window.banner.isVisible(), timeout=5000)

    ok = make_window(qtbot, FakeEngine())
    ok.check_engine()
    qtbot.wait(200)
    assert not ok.banner.isVisible()


@pytest.mark.parametrize("name", ["light", "dark"])
def test_toast_text_is_readable(qtbot: QtBot, name: theme.ThemeName) -> None:
    window = make_window(qtbot, FakeEngine())
    theme.apply(QApplication.instance(), name)  # type: ignore[arg-type]
    window.toast.show_message("Zapisano plik.", "Pokaż w folderze")
    label = window.toast.text
    label.ensurePolished()
    # The toast is dark-on-light inverted: its text must use the background colour.
    colour = label.palette().color(label.foregroundRole())
    expected = theme.color("bg")
    theme.apply(QApplication.instance(), "light")  # type: ignore[arg-type]
    assert colour == expected
