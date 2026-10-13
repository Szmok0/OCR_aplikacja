"""All user-facing Polish strings (§7.10). No Qt imports: the CLI uses this too."""

from __future__ import annotations

from lokalocr.errors import ErrorCode

APP_NAME = "LokalOCR"
APP_SUBTITLE = "OCR i konwersja dokumentów — w pełni offline"
OFFLINE_BADGE = "Offline — brak połączeń sieciowych"

ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.PASSWORD_PROTECTED: "Plik jest chroniony hasłem. Usuń zabezpieczenie i spróbuj ponownie.",
    ErrorCode.CORRUPT_FILE: "Nie udało się otworzyć pliku. Może być uszkodzony.",
    ErrorCode.UNSUPPORTED_FORMAT: "Ten format nie jest obsługiwany. Użyj PDF, PNG, JPG lub TIFF.",
    ErrorCode.FULL_MODE_UNAVAILABLE: "Tryb pełny jest niedostępny: brak lokalnych modeli. Użyj trybu podstawowego.",
    ErrorCode.LANGUAGE_DATA_MISSING: "Brak danych językowych dla wybranego języka.",
    ErrorCode.ENGINE_MISSING: "Nie znaleziono silnika OCR (Tesseract). Zainstaluj go lub użyj pełnej wersji aplikacji.",
    ErrorCode.TOO_LARGE: "Plik jest zbyt duży do przetworzenia. Spróbuj niższej rozdzielczości.",
    ErrorCode.EMPTY_RESULT: "Nie znaleziono tekstu. Sprawdź jakość skanu lub język OCR.",
    ErrorCode.CANCELLED: "Przetwarzanie anulowane.",
    ErrorCode.OUTPUT_EXISTS: "Plik wynikowy już istnieje. Wybierz inną nazwę lub zezwól na nadpisanie.",
    ErrorCode.INTERNAL: "Wystąpił nieoczekiwany błąd. Szczegóły techniczne zapisano w logu.",
}

LANGUAGE_LABELS: dict[str, str] = {
    "pol+eng": "Polski + Angielski (pol+eng)",
    "pol": "Polski",
    "eng": "Angielski",
}

LANGUAGE_NAMES: dict[str, str] = {
    "pol+eng": "polski + angielski",
    "pol": "polski",
    "eng": "angielski",
}

STAGE_LABELS: dict[str, str] = {
    "loading": "Wczytywanie pliku…",
    "preprocessing": "Obróbka obrazu…",
    "ocr": "Rozpoznawanie tekstu (OCR)…",
    "layout": "Analiza układu…",
    "export": "Eksport…",
}

ESTIMATING = "Szacowanie…"


def error_message(code: ErrorCode) -> str:
    return ERROR_MESSAGES.get(code, ERROR_MESSAGES[ErrorCode.INTERNAL])


def eta_text(seconds: float | None) -> str:
    if seconds is None:
        return f"Szacowany czas: {ESTIMATING}"
    if seconds < 60:
        return f"Szacowany czas: około {max(1, round(seconds))} s"
    return f"Szacowany czas: około {round(seconds / 60)} min"


def plural_pl(n: int, one: str, few: str, many: str) -> str:
    """Polish plural form: 1 strona, 2 strony, 5 stron, 22 strony, 12 stron."""
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
