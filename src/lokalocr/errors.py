"""Error types shared by the pipeline, CLI and UI.

Exceptions carry a stable :class:`ErrorCode`; user-facing Polish messages are
looked up by code in ``lokalocr.ui.strings_pl``. Exception text is English,
technical and must never contain document content or file names (§0.2).
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    PASSWORD_PROTECTED = "password_protected"
    CORRUPT_FILE = "corrupt_file"
    UNSUPPORTED_FORMAT = "unsupported_format"
    LANGUAGE_DATA_MISSING = "language_data_missing"
    ENGINE_MISSING = "engine_missing"
    TOO_LARGE = "too_large"
    EMPTY_RESULT = "empty_result"
    CANCELLED = "cancelled"
    OUTPUT_EXISTS = "output_exists"
    INTERNAL = "internal"


class LokalOcrError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL

    def __init__(self, detail: str = "", *, code: ErrorCode | None = None) -> None:
        if code is not None:
            self.code = code
        super().__init__(detail or self.code.value)


class PasswordProtectedError(LokalOcrError):
    code = ErrorCode.PASSWORD_PROTECTED


class CorruptFileError(LokalOcrError):
    code = ErrorCode.CORRUPT_FILE


class UnsupportedFormatError(LokalOcrError):
    code = ErrorCode.UNSUPPORTED_FORMAT


class TooLargeError(LokalOcrError):
    code = ErrorCode.TOO_LARGE


class EngineMissingError(LokalOcrError):
    code = ErrorCode.ENGINE_MISSING


class LanguageDataMissingError(LokalOcrError):
    code = ErrorCode.LANGUAGE_DATA_MISSING


class CancelledError(LokalOcrError):
    code = ErrorCode.CANCELLED


class EmptyResultError(LokalOcrError):
    code = ErrorCode.EMPTY_RESULT
