"""Basic-mode OCR via the Tesseract 5 command-line binary.

The image is piped through stdin and results come back on stdout, so no
temporary copies of the document are written to disk (§6.5). The binary is
looked up in this order: ``LOKALOCR_TESSERACT`` env var, the copy bundled with
the application, ``PATH``, and the default Windows install location.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from PIL import Image

from lokalocr.errors import (
    CancelledError,
    EngineMissingError,
    LanguageDataMissingError,
    LokalOcrError,
)
from lokalocr.model import BBox, Block, BlockType, Line, Page

__all__ = ["TesseractEngine", "find_tesseract"]

_log = logging.getLogger(__name__)

TESSERACT_ENV = "LOKALOCR_TESSERACT"
TESSDATA_ENV = "LOKALOCR_TESSDATA"

_WINDOWS_DEFAULTS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)

_POLL_SECONDS = 0.1


def _exe_name() -> str:
    return "tesseract.exe" if sys.platform == "win32" else "tesseract"


def _bundled_dirs() -> list[Path]:
    dirs = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "tesseract")
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "tesseract")
    return dirs


def find_tesseract() -> tuple[Path, Path | None]:
    """Return ``(binary, tessdata_dir_or_None)``; raise if Tesseract is missing."""
    tessdata_env = os.environ.get(TESSDATA_ENV)
    tessdata = Path(tessdata_env) if tessdata_env else None

    env = os.environ.get(TESSERACT_ENV)
    if env:
        path = Path(env)
        if path.is_file():
            return path, tessdata
        raise EngineMissingError(f"{TESSERACT_ENV} does not point to a file")

    for d in _bundled_dirs():
        exe = d / _exe_name()
        if exe.is_file():
            bundled_data = d / "tessdata"
            return exe, tessdata or (bundled_data if bundled_data.is_dir() else None)

    found = shutil.which("tesseract")
    if found:
        return Path(found), tessdata
    if sys.platform == "win32":
        for exe in _WINDOWS_DEFAULTS:
            if exe.is_file():
                return exe, tessdata
    raise EngineMissingError("tesseract binary not found")


@dataclass(frozen=True, slots=True)
class _Word:
    block: int
    par: int
    line: int
    left: int
    top: int
    width: int
    height: int
    conf: float
    text: str


class TesseractEngine:
    name = "tesseract"

    def __init__(
        self,
        binary: Path | None = None,
        tessdata_dir: Path | None = None,
        *,
        psm: int = 3,
        threads: int = 1,
    ) -> None:
        if binary is None:
            binary, found_data = find_tesseract()
            tessdata_dir = tessdata_dir or found_data
        self.binary = binary
        self.tessdata_dir = tessdata_dir
        self.psm = psm
        self.threads = threads

    # --- process helpers -----------------------------------------------------

    def _base_args(self) -> list[str]:
        args = [str(self.binary)]
        if self.tessdata_dir is not None:
            args += ["--tessdata-dir", str(self.tessdata_dir)]
        return args

    def _env(self) -> dict[str, str]:
        # Tesseract's OpenMP threads busy-wait: one thread per process is faster
        # even on an idle machine and degrades gracefully under load, while
        # several multi-threaded processes slow each other down by orders of
        # magnitude. Parallelism comes from processing pages concurrently.
        env = dict(os.environ)
        env["OMP_THREAD_LIMIT"] = str(max(1, self.threads))
        return env

    def _run(
        self,
        args: Sequence[str],
        stdin: bytes | None = None,
        cancel: threading.Event | None = None,
        timeout: float = 600.0,
    ) -> bytes:
        kwargs: dict[str, object] = {}
        if sys.platform == "win32":
            # A GUI app must not flash a console window for every page.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(
                list(args),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                **kwargs,  # type: ignore[call-overload]
            )
        except OSError as exc:
            raise EngineMissingError("tesseract could not be started") from exc

        # One communicate() call does all the I/O. Retrying communicate() after
        # a timeout is not portable (on Python 3.12 the retry stops feeding
        # stdin and Tesseract waits forever), so cancellation is handled by a
        # watcher thread that kills the process instead.
        done = threading.Event()

        def watch_cancel() -> None:
            while not done.is_set():
                if cancel is not None and cancel.wait(_POLL_SECONDS):
                    proc.kill()
                    return
                if cancel is None:
                    return

        watcher = threading.Thread(target=watch_cancel, name="tesseract-cancel", daemon=True)
        watcher.start()
        try:
            out, err = proc.communicate(input=stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise LokalOcrError("tesseract timed out") from None
        finally:
            done.set()
        if cancel is not None and cancel.is_set():
            raise CancelledError("OCR cancelled")
        if proc.returncode != 0:
            message = err.decode("utf-8", "replace")
            if "Failed loading language" in message or "Error opening data file" in message:
                raise LanguageDataMissingError("tesseract language data missing")
            # stderr may echo parts of the input path but never document text.
            _log.error("tesseract failed with exit code %s", proc.returncode)
            raise LokalOcrError(f"tesseract exited with code {proc.returncode}")
        return bytes(out)

    @staticmethod
    def _png_bytes(image: Image.Image, dpi: int) -> bytes:
        buf = io.BytesIO()
        image.save(buf, "PNG", dpi=(dpi, dpi), compress_level=1)
        return buf.getvalue()

    # --- public API ----------------------------------------------------------

    @cached_property
    def _version(self) -> str:
        out = self._run([*self._base_args(), "--version"])
        first = out.decode("utf-8", "replace").splitlines()
        return first[0].strip() if first else "tesseract"

    def version(self) -> str:
        return self._version

    def available_languages(self) -> frozenset[str]:
        out = self._run([*self._base_args(), "--list-langs"]).decode("utf-8", "replace")
        langs = {ln.strip() for ln in out.splitlines()[1:] if ln.strip()}
        return frozenset(langs - {"osd"})

    def check_languages(self, lang: str) -> None:
        missing = set(lang.split("+")) - self.available_languages()
        if missing:
            raise LanguageDataMissingError(f"missing language data: {sorted(missing)}")

    def recognize(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        page_number: int = 1,
        cancel: threading.Event | None = None,
    ) -> Page:
        args = [
            *self._base_args(),
            "stdin",
            "stdout",
            "-l",
            lang,
            "--psm",
            str(self.psm),
            "--dpi",
            str(dpi),
            "-c",
            "preserve_interword_spaces=0",
            "tsv",
        ]
        tsv = self._run(args, self._png_bytes(image, dpi), cancel)
        page = Page(number=page_number, width=image.width, height=image.height, dpi=dpi)
        page.blocks = _blocks_from_tsv(tsv.decode("utf-8", "replace"))
        return page

    def searchable_pdf(
        self,
        image: Image.Image,
        lang: str,
        *,
        dpi: int,
        cancel: threading.Event | None = None,
        jpeg_quality: int | None = 80,
    ) -> bytes:
        """Single-page PDF with the page image and an invisible text layer.

        With ``jpeg_quality`` the image goes in as JPEG, which Tesseract embeds
        without re-encoding (a few hundred KB per page instead of megabytes).
        """
        args = [
            *self._base_args(), "stdin", "stdout",
            "-l", lang, "--psm", str(self.psm), "--dpi", str(dpi),
            "pdf",
        ]  # fmt: skip
        if jpeg_quality is None:
            data = self._png_bytes(image, dpi)
        else:
            buf = io.BytesIO()
            mode = "L" if image.mode in ("L", "1") else "RGB"
            image.convert(mode).save(buf, "JPEG", quality=jpeg_quality, dpi=(dpi, dpi))
            data = buf.getvalue()
        return self._run(args, data, cancel)


def _parse_words(tsv: str) -> list[_Word]:
    words: list[_Word] = []
    reader = csv.reader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    header = next(reader, None)
    if not header:
        return words
    idx = {name: i for i, name in enumerate(header)}
    for row in reader:
        if len(row) < len(header) or row[idx["level"]] != "5":
            continue
        text = row[idx["text"]].strip()
        if not text:
            continue
        try:
            conf = float(row[idx["conf"]])
        except ValueError:
            conf = -1.0
        words.append(
            _Word(
                block=int(row[idx["block_num"]]),
                par=int(row[idx["par_num"]]),
                line=int(row[idx["line_num"]]),
                left=int(row[idx["left"]]),
                top=int(row[idx["top"]]),
                width=int(row[idx["width"]]),
                height=int(row[idx["height"]]),
                conf=conf,
                text=text,
            )
        )
    return words


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _blocks_from_tsv(tsv: str) -> list[Block]:
    """Group Tesseract words into paragraph blocks with positioned lines."""
    blocks: list[Block] = []
    current_par: tuple[int, int] | None = None
    current_line: tuple[int, int, int] | None = None
    line_words: list[_Word] = []
    par_lines: list[Line] = []

    def flush_line() -> None:
        if not line_words:
            return
        box = BBox.union([BBox(w.left, w.top, w.width, w.height) for w in line_words])
        confs = [w.conf / 100.0 for w in line_words if w.conf >= 0]
        par_lines.append(Line(" ".join(w.text for w in line_words), box, _mean(confs)))
        line_words.clear()

    def flush_par() -> None:
        flush_line()
        if not par_lines:
            return
        confs = [ln.confidence for ln in par_lines if ln.confidence is not None]
        blocks.append(
            Block(
                type=BlockType.PARAGRAPH,
                text="\n".join(ln.text for ln in par_lines),
                lines=list(par_lines),
                bbox=BBox.union([ln.bbox for ln in par_lines if ln.bbox is not None]),
                confidence=_mean(confs),
            )
        )
        par_lines.clear()

    for word in _parse_words(tsv):
        par_key = (word.block, word.par)
        line_key = (word.block, word.par, word.line)
        if par_key != current_par:
            flush_par()
            current_par = par_key
        if line_key != current_line:
            flush_line()
            current_line = line_key
        line_words.append(word)
    flush_par()
    return blocks
