from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

# Qt tests run headless everywhere (CI sets this too).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import make_fixtures as fx
from lokalocr import netguard


def pytest_sessionstart(session: pytest.Session) -> None:
    # The whole test suite runs offline, like the application (§6).
    netguard.install()


def _tesseract_ready() -> bool:
    try:
        from lokalocr.engines.tesseract import TesseractEngine

        return {"pol", "eng"} <= TesseractEngine().available_languages()
    except Exception:
        return False


TESSERACT_READY = _tesseract_ready()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not TESSERACT_READY and os.environ.get("LOKALOCR_REQUIRE_TESSERACT") == "1":
        raise pytest.UsageError("LOKALOCR_REQUIRE_TESSERACT=1 but tesseract (pol+eng) is missing")
    skip = pytest.mark.skip(reason="tesseract with pol+eng data not installed")
    for item in items:
        if "tesseract" in item.keywords and not TESSERACT_READY:
            item.add_marker(skip)


@pytest.fixture
def fresh_guard() -> Iterator[None]:
    """Give a test an uninstalled guard and reinstall it afterwards."""
    netguard.uninstall()
    yield
    netguard.uninstall()
    netguard.install()


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Synthetic documents written once per session."""
    out = tmp_path_factory.mktemp("synthetic")
    fx.save(fx.make_cv(200), out / "cv.png")
    fx.save(fx.make_cv(200), out / "cv.jpg")
    fx.save(fx.make_invoice(200), out / "invoice.png")
    contract = fx.make_contract(150, pages=2)
    fx.save(contract, out / "contract.pdf")
    fx.save(contract, out / "contract.tif")
    yield out
    shutil.rmtree(out, ignore_errors=True)
