"""Command-line interface (stage 2): ``lokalocr plik -o wynik --mode basic --lang pol+eng``.

Messages are Polish (§0.8) and go to stderr; recognised text goes only to the
output files (or stdout with ``-o -``). The network guard is installed before
anything else is imported.
"""

from __future__ import annotations

from lokalocr import netguard

netguard.install()

import argparse  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from enum import IntEnum  # noqa: E402
from pathlib import Path  # noqa: E402

from lokalocr import __version__  # noqa: E402
from lokalocr.errors import ErrorCode, LokalOcrError  # noqa: E402
from lokalocr.exporters.common import default_output_name  # noqa: E402
from lokalocr.exporters.txt import export_txt, to_txt  # noqa: E402
from lokalocr.loader import SUPPORTED_EXTENSIONS  # noqa: E402
from lokalocr.logsafe import log_unexpected  # noqa: E402
from lokalocr.pipeline import LANGUAGES, Pipeline, ProcessOptions, ProgressEvent  # noqa: E402
from lokalocr.preprocess import PreprocessOptions  # noqa: E402
from lokalocr.ui.strings_pl import STAGE_LABELS, error_message  # noqa: E402

__all__ = ["ExitCode", "main"]

_log = logging.getLogger(__name__)


class ExitCode(IntEnum):
    OK = 0
    SOME_FAILED = 1
    USAGE = 2
    ENGINE_MISSING = 3
    CANCELLED = 130


FORMATS = ("txt",)


@dataclass(frozen=True, slots=True)
class Job:
    source: Path
    target: Path | None  # None = stdout


def _collect_inputs(paths: Sequence[Path], recursive: bool) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    problems: list[str] = []
    for path in paths:
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            found = sorted(
                p
                for p in path.glob(pattern)
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            if not found:
                problems.append(f"{path}: brak obsługiwanych plików w folderze")
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            problems.append(f"{path}: nie znaleziono pliku")
    return files, problems


def _plan(files: list[Path], output: str | None, fmt: str) -> list[Job]:
    if output == "-":
        return [Job(f, None) for f in files]
    if output is None:
        return [Job(f, f.with_name(default_output_name(f, fmt))) for f in files]
    out = Path(output)
    if len(files) == 1 and not out.is_dir() and out.suffix:
        return [Job(files[0], out)]
    return [Job(f, out / default_output_name(f, fmt)) for f in files]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lokalocr",
        description="LokalOCR — rozpoznawanie tekstu w dokumentach, w pełni offline.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        metavar="PLIK_LUB_FOLDER",
        help="pliki PDF, PNG, JPG, TIFF lub foldery z takimi plikami",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="WYNIK",
        help="plik wynikowy (dla jednego pliku), folder wynikowy albo „-” "
        "(standardowe wyjście); domyślnie obok pliku źródłowego",
    )
    parser.add_argument(
        "--mode",
        choices=("basic", "full"),
        default="basic",
        help="tryb pracy: basic = podstawowy, full = pełny (domyślnie basic)",
    )
    parser.add_argument(
        "--lang", choices=LANGUAGES, default="pol+eng", help="język OCR (domyślnie pol+eng)"
    )
    parser.add_argument(
        "--format", choices=FORMATS, default="txt", dest="fmt", help="format wyniku (domyślnie txt)"
    )
    parser.add_argument(
        "--layout",
        choices=("simplified", "original"),
        default="simplified",
        help="tekst uproszczony albo oryginalny układ (domyślnie simplified)",
    )
    parser.add_argument(
        "--dpi", type=int, default=300, help="rozdzielczość renderowania PDF (domyślnie 300)"
    )
    parser.add_argument(
        "--no-preprocess", action="store_true", help="wyłącz automatyczną obróbkę obrazu"
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="przeszukuj foldery rekurencyjnie"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="nadpisuj istniejące pliki wynikowe"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="bez komunikatów o postępie")
    parser.add_argument("--version", action="version", version=f"LokalOCR {__version__}")
    return parser


def _say(message: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if not 72 <= args.dpi <= 1200:
        parser.error("--dpi musi mieścić się w zakresie 72–1200")
    if args.mode == "full":
        _say(error_message(ErrorCode.FULL_MODE_UNAVAILABLE))
        return ExitCode.USAGE

    files, problems = _collect_inputs(args.inputs, args.recursive)
    for problem in problems:
        _say(problem)
    if not files:
        return ExitCode.USAGE
    if args.output == "-" and len(files) > 1:
        parser.error("„-o -” działa tylko dla jednego pliku")
    jobs = _plan(files, args.output, args.fmt)

    try:
        from lokalocr.engines.tesseract import TesseractEngine

        engine = TesseractEngine()
        engine.check_languages(args.lang)
    except LokalOcrError as exc:
        _say(error_message(exc.code))
        return ExitCode.ENGINE_MISSING

    pipeline = Pipeline(engine)
    options = ProcessOptions(
        lang=args.lang,
        mode="basic",
        pdf_dpi=args.dpi,
        preprocess=PreprocessOptions(enabled=not args.no_preprocess),
    )
    cancel = threading.Event()
    failed = 0
    for n, job in enumerate(jobs, start=1):
        prefix = f"[{n}/{len(jobs)}] {job.source.name}"
        if job.target is not None and job.target.exists() and not args.overwrite:
            _say(f"{prefix}: {error_message(ErrorCode.OUTPUT_EXISTS)}")
            failed += 1
            continue

        def progress(event: ProgressEvent, prefix: str = prefix) -> None:
            # One line per page, when its OCR starts.
            if event.stage == "ocr" and event.page and event.percent < 100:
                _say(
                    f"{prefix}: strona {event.page}/{event.page_count} — "
                    f"{STAGE_LABELS[event.stage]}",
                    quiet=args.quiet,
                )

        try:
            document = pipeline.process(job.source, options, on_progress=progress, cancel=cancel)
            if job.target is None:
                sys.stdout.write(to_txt(document, args.layout))
                sys.stdout.flush()
            else:
                export_txt(document, job.target, layout=args.layout, overwrite=args.overwrite)
                _say(f"{prefix}: zapisano {job.target}", quiet=args.quiet)
        except KeyboardInterrupt:
            cancel.set()
            _say(error_message(ErrorCode.CANCELLED))
            return ExitCode.CANCELLED
        except LokalOcrError as exc:
            _say(f"{prefix}: {error_message(exc.code)}")
            failed += 1
        except Exception as exc:
            log_unexpected(_log, exc, "cli")
            _say(f"{prefix}: {error_message(ErrorCode.INTERNAL)}")
            failed += 1
    if failed:
        _say(f"Nie udało się przetworzyć plików: {failed} z {len(jobs)}.")
        return ExitCode.SOME_FAILED
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
