from __future__ import annotations

import json
from pathlib import Path

import pytest

from lokalocr import config
from lokalocr.config import Settings


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(default_lang="pol", theme="dark", output_dir=str(tmp_path), threads=2)
    config.save(s, path)
    assert config.load(path) == s


def test_missing_or_broken_file_gives_defaults(tmp_path: Path) -> None:
    assert config.load(tmp_path / "nope.json") == Settings()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert config.load(broken) == Settings()
    broken.write_text("[1, 2]", encoding="utf-8")
    assert config.load(broken) == Settings()


def test_invalid_values_fall_back(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {
                "pdf_dpi": 7,
                "theme": "neon",
                "name_pattern": "bez",
                "unknown_key": 1,
                "default_lang": "deu",
            }
        ),
        encoding="utf-8",
    )
    s = config.load(path)
    assert (s.pdf_dpi, s.theme, s.name_pattern, s.default_lang) == (
        300,
        "system",
        "{nazwa}_ocr",
        "pol+eng",
    )


def test_settings_never_store_document_names(tmp_path: Path) -> None:
    path = config.save(Settings(), tmp_path / "s.json")
    keys = set(json.loads(path.read_text(encoding="utf-8")))
    assert not any("recent" in k or "history" in k or "queue" in k for k in keys)


@pytest.mark.parametrize(
    ("pattern", "stem", "expected"),
    [
        ("{nazwa}_ocr", "umowa", "umowa_ocr.docx"),
        ("OCR - {nazwa}", "faktura 2024", "OCR - faktura 2024.docx"),
        ("{nazwa}:x?", "cv", "cv_x_.docx"),
    ],
)
def test_output_name(pattern: str, stem: str, expected: str) -> None:
    assert Settings(name_pattern=pattern).output_name(stem, "docx") == expected


def test_worker_count() -> None:
    assert Settings(threads=3).worker_count() == 3
    assert 1 <= Settings().worker_count() <= 4


def test_config_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(config.CONFIG_ENV, str(tmp_path))
    assert config.config_path() == tmp_path / "settings.json"
    assert config.log_dir() == tmp_path / "logs"
