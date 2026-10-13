"""Main window tests (stage 3), run offscreen with a controllable fake engine."""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
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
    assert not window.save_txt_btn.isEnabled()
    assert window.result.empty_title.text() == S.EMPTY_RESULT_TITLE


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
    assert window.save_txt_btn.isEnabled()


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
