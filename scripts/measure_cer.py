"""Measure OCR quality (CER/WER) on the synthetic fixture set (CLAUDE.md §9, §11).

Usage::

    python scripts/measure_cer.py                       # default options
    python scripts/measure_cer.py --write docs/quality/cer-baseline.md
    python scripts/measure_cer.py --compare             # preprocessing ablation

Runs entirely offline (network guard active).
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

from rapidfuzz.distance import Levenshtein

import make_fixtures as fx
from lokalocr import netguard
from lokalocr.engines.tesseract import TesseractEngine
from lokalocr.pipeline import Pipeline, ProcessOptions
from lokalocr.preprocess import PreprocessOptions
from lokalocr.textview import simplified

_WS = re.compile(r"\s+")
_BULLETS = re.compile(r"[•●▪◦]")


def normalize(text: str) -> str:
    return _WS.sub(" ", _BULLETS.sub(" ", text)).strip()


def cer(truth: str, hypothesis: str) -> float:
    t, h = normalize(truth), normalize(hypothesis)
    return Levenshtein.distance(t, h) / max(1, len(t))


def wer(truth: str, hypothesis: str) -> float:
    t, h = normalize(truth).split(), normalize(hypothesis).split()
    return Levenshtein.distance(t, h) / max(1, len(t))


@dataclass(frozen=True)
class Result:
    document: str
    dpi: int
    variant: str
    cer: float
    wer: float
    seconds_per_page: float


def run(
    engine: TesseractEngine,
    options: ProcessOptions,
    documents: list[str],
    dpis: list[int],
    variants: list[str],
    workdir: Path,
) -> list[Result]:
    pipeline = Pipeline(engine)
    results = []
    for name in documents:
        for dpi in dpis:
            base = fx.DOCUMENTS[name](dpi)
            for variant in variants:
                doc = fx.degrade(base, variant)
                ext = ".pdf" if len(doc.pages) > 1 else ".png"
                path = fx.save(doc, workdir / f"{doc.name}_{dpi}{ext}")
                started = time.monotonic()
                result = pipeline.process(path, replace(options, pdf_dpi=dpi))
                elapsed = (time.monotonic() - started) / len(doc.pages)
                text = simplified(result)
                results.append(
                    Result(name, dpi, variant, cer(doc.truth, text), wer(doc.truth, text), elapsed)
                )
                path.unlink()
    return results


def table(results: list[Result]) -> str:
    rows = ["| Dokument | DPI | Wariant | CER | WER | s/strona |", "|---|---|---|---|---|---|"]
    rows += [
        f"| {r.document} | {r.dpi} | {r.variant} | {r.cer:.2%} | {r.wer:.2%} "
        f"| {r.seconds_per_page:.1f} |"
        for r in results
    ]
    mean_cer = sum(r.cer for r in results) / len(results)
    rows.append(f"| **średnio** | | | **{mean_cer:.2%}** | | |")
    return "\n".join(rows)


ABLATIONS: dict[str, PreprocessOptions] = {
    "brak obróbki": PreprocessOptions(enabled=False),
    "tylko skalowanie": PreprocessOptions(deskew=False, denoise=False, contrast=False),
    "bez odszumiania": PreprocessOptions(denoise=False),
    "bez prostowania": PreprocessOptions(deskew=False),
    "bez kontrastu": PreprocessOptions(contrast=False),
    "domyślne": PreprocessOptions(),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--documents", nargs="+", default=list(fx.DOCUMENTS))
    parser.add_argument("--dpi", nargs="+", type=int, default=[150, 200, 300])
    parser.add_argument("--variants", nargs="+", default=list(fx.VARIANTS))
    parser.add_argument("--lang", default="pol+eng")
    parser.add_argument("--compare", action="store_true", help="preprocessing ablation")
    parser.add_argument("--write", type=Path, help="write a Markdown report here")
    args = parser.parse_args(argv)

    netguard.install()
    engine = TesseractEngine()
    sections = [f"Silnik: `{engine.version()}`, język: `{args.lang}`.\n"]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if args.compare:
            for label, pre in ABLATIONS.items():
                res = run(
                    engine,
                    ProcessOptions(lang=args.lang, preprocess=pre),
                    args.documents,
                    args.dpi,
                    args.variants,
                    work,
                )
                mean = sum(r.cer for r in res) / len(res)
                worst = max(res, key=lambda r: r.cer)
                line = (
                    f"- **{label}**: średni CER {mean:.2%}, najgorszy {worst.cer:.2%} "
                    f"({worst.document}/{worst.dpi}/{worst.variant}), "
                    f"{sum(r.seconds_per_page for r in res) / len(res):.1f} s/strona"
                )
                print(line, flush=True)
                sections.append(line)
        else:
            res = run(
                engine,
                ProcessOptions(lang=args.lang),
                args.documents,
                args.dpi,
                args.variants,
                work,
            )
            sections.append(table(res))
            print(sections[-1])
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
