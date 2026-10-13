"""Download the full-mode (Docling) models into ``models/docling`` — developer machine only.

This is the only part of the project allowed to use the network (§0.1, §6.4).
It runs with the network guard disabled, downloads the layout and table
structure models through Docling's own downloader, and writes
``MANIFEST.json`` with the size and SHA-256 of every file. The application
only accepts a model folder whose files match the manifest.

Usage::

    pip install -e ".[full]"
    python scripts/fetch_models.py [--out models]
    python scripts/fetch_models.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ["LOKALOCR_ALLOW_NET"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)

MANIFEST = "MANIFEST.json"
SKIP = {MANIFEST, ".gitattributes"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(folder: Path) -> Path:
    files = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if rel in SKIP or "/.cache/" in f"/{rel}" or rel.startswith(".cache/"):
            continue
        files.append({"path": rel, "size": path.stat().st_size, "sha256": sha256(path)})
    manifest = folder / MANIFEST
    manifest.write_text(json.dumps({"files": files}, indent=2), encoding="utf-8")
    return manifest


def verify(folder: Path) -> list[str]:
    data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    problems = []
    for entry in data["files"]:
        path = folder / entry["path"]
        if not path.is_file():
            problems.append(f"missing: {entry['path']}")
        elif path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
            problems.append(f"checksum mismatch: {entry['path']}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("models"))
    parser.add_argument("--verify", action="store_true", help="only verify checksums")
    args = parser.parse_args(argv)
    folder = args.out / "docling"

    if args.verify:
        problems = verify(folder)
        for problem in problems:
            print(problem, file=sys.stderr)
        print("OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0

    from docling.utils.model_downloader import download_models

    folder.mkdir(parents=True, exist_ok=True)
    download_models(
        output_dir=folder,
        progress=True,
        with_layout=True,
        with_tableformer=True,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=False,
        with_easyocr=False,
    )
    manifest = write_manifest(folder)
    total = sum(e["size"] for e in json.loads(manifest.read_text(encoding="utf-8"))["files"])
    print(f"Models in {folder} ({total / 1e6:.0f} MB), manifest: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
