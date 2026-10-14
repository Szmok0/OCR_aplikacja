"""Full-mode model detection (no Docling needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lokalocr.engines import docling_engine


def _install(root: Path, files: dict[str, bytes], listed: dict[str, int]) -> Path:
    folder = root / "docling"
    for rel, data in files.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    entries = [{"path": rel, "size": size, "sha256": "-"} for rel, size in listed.items()]
    (folder / docling_engine.MANIFEST).write_text(json.dumps({"files": entries}), encoding="utf-8")
    return folder


@pytest.fixture
def models_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(docling_engine, "_candidate_model_dirs", lambda: [tmp_path])
    return tmp_path


def test_complete_models_are_found(models_root: Path) -> None:
    folder = _install(models_root, {"repo/model.bin": b"abc"}, {"repo/model.bin": 3})
    assert docling_engine.find_models_dir() == folder


def test_missing_or_truncated_model_file_is_detected(models_root: Path) -> None:
    _install(models_root, {"repo/model.bin": b"ab"}, {"repo/model.bin": 3, "repo/x.json": 2})
    assert docling_engine.find_models_dir() is None


def test_dot_files_dropped_in_transit_do_not_disable_full_mode(models_root: Path) -> None:
    # Older manifests list git metadata of the model repositories; CI artifacts
    # and some archivers drop dot-files, which disabled full mode in the package.
    listed = {"repo/.gitattributes": 10, "repo/.gitignore": 5, "repo/model.bin": 3}
    folder = _install(models_root, {"repo/model.bin": b"abc"}, listed)
    assert docling_engine.find_models_dir() == folder
