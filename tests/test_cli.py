from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest
from PIL import Image

from lokalocr import cli, netguard
from lokalocr.engines import tesseract
from lokalocr.model import BBox, Block, BlockType, Line, Page


class FakeEngine:
    name = "fake"

    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def recognize(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        page_number: int = 1,
        cancel: threading.Event | None = None,
    ) -> Page:
        line = Line(f"Strona {page_number} zażółć", BBox(0, 0, 100, 10), 0.9)
        return Page(
            page_number,
            image.width,
            image.height,
            dpi,
            [Block(BlockType.PARAGRAPH, line.text, [line], line.bbox, 0.9)],
        )

    def check_languages(self, lang: str) -> None:
        pass

    def available_languages(self) -> frozenset[str]:
        return frozenset({"pol", "eng"})

    def version(self) -> str:
        return "fake"


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tesseract, "TesseractEngine", FakeEngine)


@pytest.fixture
def workdir(tmp_path: Path, fixtures_dir: Path) -> Path:
    for name in ("cv.png", "contract.pdf"):
        shutil.copy(fixtures_dir / name, tmp_path / name)
    (tmp_path / "notatki.txt").write_text("nie dokument", encoding="utf-8")
    return tmp_path


@pytest.mark.usefixtures("fake_engine")
def test_single_file_default_output_next_to_source(workdir: Path) -> None:
    assert cli.main([str(workdir / "cv.png"), "-q"]) == cli.ExitCode.OK
    assert "zażółć" in (workdir / "cv_ocr.txt").read_text(encoding="utf-8")


@pytest.mark.usefixtures("fake_engine")
def test_explicit_output_file(workdir: Path) -> None:
    target = workdir / "out" / "wynik.txt"
    assert cli.main([str(workdir / "contract.pdf"), "-o", str(target), "-q"]) == 0
    text = target.read_text(encoding="utf-8")
    assert "Strona 1" in text and "Strona 2" in text


@pytest.mark.usefixtures("fake_engine")
def test_batch_folder_into_output_folder(
    workdir: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    out = tmp_path_factory.mktemp("out")
    assert cli.main([str(workdir), "-o", str(out), "-q"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["contract_ocr.txt", "cv_ocr.txt"]


@pytest.mark.usefixtures("fake_engine")
def test_stdout_output(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(workdir / "cv.png"), "-o", "-", "-q"]) == 0
    assert "zażółć" in capsys.readouterr().out
    assert not (workdir / "cv_ocr.txt").exists()


@pytest.mark.usefixtures("fake_engine")
def test_existing_output_is_not_overwritten(
    workdir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = workdir / "cv_ocr.txt"
    target.write_text("stare", encoding="utf-8")
    assert cli.main([str(workdir / "cv.png")]) == cli.ExitCode.SOME_FAILED
    assert target.read_text(encoding="utf-8") == "stare"
    assert "już istnieje" in capsys.readouterr().err
    assert cli.main([str(workdir / "cv.png"), "--overwrite", "-q"]) == 0
    assert "zażółć" in target.read_text(encoding="utf-8")


@pytest.mark.usefixtures("fake_engine")
def test_corrupt_file_in_batch(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (workdir / "zepsuty.pdf").write_bytes(b"%PDF-1.7 broken")
    assert cli.main([str(workdir), "-q"]) == cli.ExitCode.SOME_FAILED
    err = capsys.readouterr().err
    assert "Może być uszkodzony" in err
    assert "1 z 3" in err
    assert (workdir / "cv_ocr.txt").exists()


@pytest.mark.usefixtures("fake_engine")
def test_missing_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(tmp_path / "brak.pdf")]) == cli.ExitCode.USAGE
    assert "nie znaleziono" in capsys.readouterr().err


def test_full_mode_not_available_yet(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(workdir / "cv.png"), "--mode", "full"]) == cli.ExitCode.USAGE
    assert "Tryb pełny jest niedostępny" in capsys.readouterr().err


def test_engine_missing(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(tesseract.TESSERACT_ENV, str(workdir / "brak-tesseract.exe"))
    assert cli.main([str(workdir / "cv.png")]) == cli.ExitCode.ENGINE_MISSING
    assert "Tesseract" in capsys.readouterr().err


def test_usage_errors(workdir: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([str(workdir / "cv.png"), "--dpi", "10"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        cli.main([str(workdir), "-o", "-"])


@pytest.mark.tesseract
def test_end_to_end_with_network_guard(workdir: Path) -> None:
    assert netguard.is_installed()
    assert cli.main([str(workdir / "cv.png"), "--layout", "original", "-q"]) == 0
    text = (workdir / "cv_ocr.txt").read_text(encoding="utf-8")
    assert "Przykładowa" in text and "WYKSZTAŁCENIE" in text
