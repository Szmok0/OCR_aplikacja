"""User settings (§7.5) stored as JSON in the per-user config folder.

The file never contains document names or source paths (§6.7): only the
output folder the user chose and an optional custom temp folder.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal

from lokalocr.model import Mode
from lokalocr.preprocess import PreprocessOptions

__all__ = [
    "APP_DIR_NAME",
    "Settings",
    "config_dir",
    "config_path",
    "load",
    "log_dir",
    "save",
]

_log = logging.getLogger(__name__)

APP_DIR_NAME = "LokalOCR"
CONFIG_ENV = "LOKALOCR_CONFIG_DIR"  # tests and portable setups

ThemeChoice = Literal["system", "light", "dark"]
OutputFormat = Literal["docx", "txt", "pdf", "md", "html"]
LogLevel = Literal["warning", "info", "debug"]

LANGUAGES = ("pol+eng", "pol", "eng")
PDF_DPI_CHOICES = (150, 200, 300, 400, 600)
NAME_PLACEHOLDER = "{nazwa}"


def config_dir() -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "lokalocr"


def log_dir() -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override) / "logs"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_DIR_NAME / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_DIR_NAME
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "lokalocr" / "logs"


def config_path() -> Path:
    return config_dir() / "settings.json"


@dataclass
class Settings:
    # OCR
    default_lang: str = "pol+eng"
    default_mode: Mode = "basic"
    # Processing
    auto_preprocess: bool = True
    deskew: bool = True
    denoise: bool = True
    contrast: bool = True
    pdf_dpi: int = 300
    threads: int = 0  # 0 = automatic
    # Output
    output_dir: str = ""  # "" = ask every time
    name_pattern: str = "{nazwa}_ocr"
    default_format: OutputFormat = "docx"
    keep_structure: bool = True
    temp_dir: str = ""  # "" = system default
    clipboard_clear_minutes: int = 0  # 0 = never
    # Appearance
    theme: ThemeChoice = "system"
    font_size: float = 0.0  # 0 = system default
    ui_language: str = "pl"
    # Advanced
    log_level: LogLevel = "warning"

    def preprocess_options(self) -> PreprocessOptions:
        return PreprocessOptions(
            enabled=self.auto_preprocess,
            deskew=self.deskew,
            denoise=self.denoise,
            contrast=self.contrast,
        )

    def worker_count(self) -> int:
        if self.threads > 0:
            return self.threads
        cores = os.cpu_count() or 2
        # Leave a core for the UI; Tesseract runs single-threaded per page.
        return max(1, min(4, cores - 1))

    def output_name(self, stem: str, extension: str) -> str:
        pattern = self.name_pattern if NAME_PLACEHOLDER in self.name_pattern else "{nazwa}_ocr"
        name = pattern.replace(NAME_PLACEHOLDER, stem)
        name = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name).strip(" .")
        return f"{name or stem}.{extension.lstrip('.')}"

    def validated(self) -> Settings:
        """Return a copy with out-of-range values replaced by defaults."""
        default = Settings()
        out = Settings(**asdict(self))
        if out.default_lang not in LANGUAGES:
            out.default_lang = default.default_lang
        if out.default_mode not in ("basic", "full"):
            out.default_mode = default.default_mode
        if out.pdf_dpi not in PDF_DPI_CHOICES:
            out.pdf_dpi = default.pdf_dpi
        if not 0 <= out.threads <= 64:
            out.threads = default.threads
        if out.default_format not in ("docx", "txt", "pdf", "md", "html"):
            out.default_format = default.default_format
        if NAME_PLACEHOLDER not in out.name_pattern:
            out.name_pattern = default.name_pattern
        if not 0 <= out.clipboard_clear_minutes <= 240:
            out.clipboard_clear_minutes = default.clipboard_clear_minutes
        if out.theme not in ("system", "light", "dark"):
            out.theme = default.theme
        if out.font_size and not 7 <= out.font_size <= 24:
            out.font_size = default.font_size
        if out.log_level not in ("warning", "info", "debug"):
            out.log_level = default.log_level
        if out.ui_language != "pl":
            out.ui_language = default.ui_language
        return out


def load(path: Path | None = None) -> Settings:
    target = path or config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError):
        _log.warning("Settings file unreadable; using defaults")
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    values: dict[str, Any] = {k: v for k, v in raw.items() if k in known}
    try:
        return Settings(**values).validated()
    except TypeError:
        return Settings()


def save(settings: Settings, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(asdict(settings.validated()), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, target)
    return target
