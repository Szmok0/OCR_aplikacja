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


# --- main window (stage 3) ----------------------------------------------------------

OFFLINE_TIP = (
    "Aplikacja nie łączy się z internetem. Wszystkie dokumenty są przetwarzane "
    "wyłącznie na tym komputerze."
)
SETTINGS = "Ustawienia"
SETTINGS_TIP = "Ustawienia aplikacji (Ctrl+,)"
HELP = "Pomoc"
HELP_TIP = "Pomoc i informacje o programie (F1)"

DROP_TITLE = "Upuść pliki tutaj"
DROP_FORMATS = "PDF, PNG, JPG, TIFF"
DROP_HINT = "lub kliknij, aby wybrać pliki"
CHOOSE_FILES = "Wybierz pliki…"
CHOOSE_FILES_TIP = "Wybierz dokumenty do rozpoznania (Ctrl+O)"
CHOOSE_FILES_DIALOG = "Wybierz dokumenty"
FILE_FILTER = "Dokumenty i obrazy"

QUEUE_TITLE = "Kolejka plików"
QUEUE_EMPTY = "Kolejka jest pusta. Dodaj pliki, aby rozpocząć (Ctrl+O)."
CLEAR = "Wyczyść"
CLEAR_TIP = "Usuń wszystkie pliki z kolejki i wyczyść pliki tymczasowe"
STATUS_DONE = "Gotowe"
STATUS_WAITING = "Oczekuje"
STATUS_PROCESSING = "Przetwarzanie…"
MENU_SHOW_RESULT = "Pokaż wynik"
MENU_REPROCESS = "Przetwórz ponownie"
MENU_REMOVE = "Usuń z kolejki"

QUICK_SETTINGS = "Ustawienia szybkiego przetwarzania"
OCR_LANGUAGE = "Język OCR"
WORK_MODE = "Tryb pracy"
MODE_BASIC = "Podstawowy"
MODE_FULL = "Pełny"
MODE_BASIC_TIP = "Czysty tekst. Działa na każdym komputerze."
MODE_FULL_TIP = (
    "Odtwarza strukturę dokumentu (nagłówki, listy, tabele, obrazy) i zapisuje "
    "edytowalny DOCX. To czysty dokument do dalszej pracy, a nie kopia wyglądu strony 1:1."
)
MODE_FULL_UNAVAILABLE = (
    "Tryb pełny jest niedostępny: brak lokalnych modeli. Użyj trybu podstawowego."
)
AUTO_PREPROCESS = "Automatyczna obróbka obrazu"
AUTO_PREPROCESS_TIP = "Prostowanie, usuwanie szumów i poprawa kontrastu przed rozpoznaniem tekstu"

WORKSPACE_EMPTY_TITLE = "Podgląd strony"
WORKSPACE_EMPTY_HINT = "Podgląd oryginału pojawi się tutaj po dodaniu pliku."

LAYOUT_ORIGINAL = "Oryginalny układ"
LAYOUT_SIMPLIFIED = "Tekst uproszczony"
LAYOUT_ORIGINAL_TIP = "Zachowuje podział na linie i przybliżone położenie tekstu"
LAYOUT_SIMPLIFIED_TIP = "Łączy linie w akapity — wygodne do dalszej edycji"
SEARCH_PLACEHOLDER = "Szukaj w tekście…"
SEARCH_PREV = "Poprzedni wynik (Shift+Enter)"
SEARCH_NEXT = "Następny wynik (Enter)"
SEARCH_NO_HITS = "Brak wyników wyszukiwania"
MORE_OPTIONS = "Więcej opcji"
SELECT_ALL = "Zaznacz wszystko"
WRAP_LINES = "Zawijanie wierszy"
COPY_TEXT = "Kopiuj tekst"
COPY_TEXT_TIP = "Kopiuj zaznaczenie albo cały widoczny tekst do schowka"
COPY_VISIBLE = "Kopiuj widoczny tekst"
COPIED = "Skopiowano tekst do schowka."
RESULT_TEXT_NAME = "Rozpoznany tekst"

EMPTY_RESULT_TITLE = "Brak wyniku"
EMPTY_RESULT_HINT = "Przeciągnij plik do okna albo naciśnij Ctrl+O, aby wybrać dokument."
WAITING_TITLE = "Plik czeka w kolejce"
PROCESSING_TITLE = "Trwa przetwarzanie…"
CANCEL = "Anuluj"
CANCEL_TIP = "Przerwij przetwarzanie (Esc)"
CANCEL_QUESTION = "Przerwać przetwarzanie tego pliku?"
CANCEL_KEEP = "Zostaw w kolejce"
CANCEL_REMOVE = "Usuń z kolejki"
CANCEL_CONTINUE = "Kontynuuj"

SAVE_TXT = "Zapisz jako TXT"
SAVE_TXT_TIP = "Zapisz widoczny tekst do pliku (Ctrl+S)"
SAVE_DIALOG_TITLE = "Zapisz wynik"
FILTER_TXT = "Plik tekstowy"
SAVE_FAILED = (
    "Nie udało się zapisać pliku. Sprawdź, czy folder istnieje i czy masz do niego dostęp."
)
SHOW_IN_FOLDER = "Pokaż w folderze"


def queue_title(n: int) -> str:
    return f"{QUEUE_TITLE} ({n})"


def waiting_hint(name: str) -> str:
    return f"„{name}” zostanie przetworzony, gdy przyjdzie jego kolej."


def page_of(page: int, total: int) -> str:
    return f"(strona {page} z {total})"


def status_line(pages: int, words: int, lang: str, confidence: float | None) -> str:
    conf = f"{round(confidence * 100)}%" if confidence is not None else "—"
    page_word = "Strona 1 z 1" if pages == 1 else f"Stron: {pages}"
    words_word = plural_pl(words, "słowo", "słowa", "słów")
    return (
        f"{page_word} • Znaleziono {words} {words_word} • "
        f"Język OCR: {LANGUAGE_NAMES.get(lang, lang)} • Pewność OCR: {conf}"
    )


def search_hits(current: int, total: int) -> str:
    return f"Wynik {current} z {total}"


def short_error(code: ErrorCode | None) -> str:
    return SHORT_ERRORS.get(code, "Błąd") if code else "Błąd"


SHORT_ERRORS: dict[ErrorCode, str] = {
    ErrorCode.PASSWORD_PROTECTED: "Błąd: plik chroniony hasłem",
    ErrorCode.CORRUPT_FILE: "Błąd: uszkodzony plik",
    ErrorCode.UNSUPPORTED_FORMAT: "Błąd: nieobsługiwany format",
    ErrorCode.LANGUAGE_DATA_MISSING: "Błąd: brak danych językowych",
    ErrorCode.ENGINE_MISSING: "Błąd: brak silnika OCR",
    ErrorCode.TOO_LARGE: "Błąd: plik zbyt duży",
    ErrorCode.EMPTY_RESULT: "Nie znaleziono tekstu",
    ErrorCode.FULL_MODE_UNAVAILABLE: "Błąd: tryb pełny niedostępny",
    ErrorCode.INTERNAL: "Błąd przetwarzania",
}


def rejected_files(n: int) -> str:
    return f"Pominięto nieobsługiwane pliki: {n}. Użyj PDF, PNG, JPG lub TIFF."


def saved_as(name: str) -> str:
    return f"Zapisano: {name}"


# --- preview, tabs, export (stage 4) -------------------------------------------------

PREV_PAGE = "Poprzednia strona (PgUp)"
NEXT_PAGE = "Następna strona (PgDn)"
PAGE_NUMBER = "Numer strony"
ZOOM_OUT = "Pomniejsz (Ctrl+-)"
ZOOM_IN = "Powiększ (Ctrl++)"
FIT = "Dopasuj do okna"
HAND_TOOL = "Rączka — przesuwanie strony"
MAGNIFIER_TOOL = "Lupa — kliknij, aby powiększyć; prawy przycisk pomniejsza"
ROTATE_LEFT = "Obróć w lewo"
ROTATE_RIGHT = "Obróć w prawo"
DESKEW = "Prostuj stronę w podglądzie"
PREVIEW_FAILED = "Nie udało się wyświetlić podglądu tej strony."

TAB_TEXT = "Tekst"
TAB_PREVIEW = "Podgląd"
TAB_TEXT_TIP = "Podgląd oryginału obok rozpoznanego tekstu"
TAB_PREVIEW_TIP = "Podgląd strony na całą szerokość z ramkami rozpoznanych bloków"
TAB_IMAGES_TIP = "Obrazy wyciągnięte z dokumentu (tryb pełny)"
STRUCTURE = "Struktura"
STRUCTURE_TIP = "Struktura dokumentu: nagłówki, akapity, listy, tabele i obrazy"
STRUCTURE_UNAVAILABLE = "Struktura dokumentu jest dostępna w trybie pełnym."
IMAGES_UNAVAILABLE = "Obrazy są wyciągane w trybie pełnym."

FORMAT_LABELS: dict[str, str] = {
    "docx": "DOCX",
    "txt": "TXT",
    "pdf": "PDF (z tekstem)",
    "md": "Markdown",
    "html": "HTML",
}
FORMAT_FILTERS: dict[str, str] = {
    "docx": "Dokument Word (*.docx)",
    "txt": "Plik tekstowy (*.txt)",
    "pdf": "PDF z warstwą tekstową (*.pdf)",
    "md": "Markdown (*.md)",
    "html": "Strona HTML (*.html)",
}
FORMAT_TIPS: dict[str, str] = {
    "docx": "Edytowalny dokument Word — czysty dokument, nie kopia wyglądu strony",
    "txt": "Czysty tekst w kodowaniu UTF-8",
    "pdf": "Oryginalne strony z ukrytą warstwą tekstu — tekst można zaznaczać i wyszukiwać",
    "md": "Markdown — tekst z prostym formatowaniem",
    "html": "Strona HTML do otwarcia w przeglądarce (bez zasobów z internetu)",
}
SAVE_AS_MENU = "Zapisz jako"
OPEN_IMAGES_TIP = "Otwórz folder z obrazami wyciągniętymi z dokumentu"
OUTPUT_OPTIONS = "Opcje wyniku (dla tego dokumentu)"
CLEAN_TEXT_ALWAYS = "Czysty tekst (zawsze)"
CLEAN_TEXT_TIP = "Rozpoznany tekst jest zawsze częścią wyniku."
KEEP_STRUCTURE = "Zachowaj strukturę (tryb pełny)"
KEEP_STRUCTURE_TIP = (
    "W trybie pełnym DOCX, Markdown i HTML zawierają nagłówki, listy, tabele i obrazy. "
    "Po wyłączeniu zapisywany jest czysty tekst w akapitach."
)
EXPORTING_TITLE = "Trwa zapisywanie…"
EXPORT_CANCELLED = "Zapis przerwany."
EXPORT_BUSY = "Trwa zapisywanie innego pliku. Poczekaj na jego zakończenie."


def save_as(fmt: str) -> str:
    return f"Zapisz jako {FORMAT_LABELS[fmt].split(' ')[0]}"


def tab_images(n: int) -> str:
    return f"Obrazy ({n})"


def open_images(n: int) -> str:
    return f"Otwórz folder z obrazami ({n})"


# --- settings, help, about (stage 5) ---------------------------------------------

OK = "OK"
CLOSE = "Zamknij"
HELP_TITLE = "LokalOCR — pomoc"
HELP_MISSING = "Nie znaleziono pliku pomocy dołączonego do aplikacji."
SETTINGS_CATEGORIES: dict[str, str] = {
    "ocr": "OCR",
    "processing": "Przetwarzanie",
    "output": "Wyjście",
    "appearance": "Wygląd",
    "advanced": "Zaawansowane",
    "about": "O programie",
}
SETTINGS_OCR_TITLE = "Ustawienia OCR"
DEFAULT_LANGUAGE = "Język OCR (domyślny)"
DEFAULT_MODE = "Tryb pracy (domyślny)"
COMPONENT_STATUS = "Stan komponentów"
FULL_MODE_MODELS = "Modele trybu pełnego"
LANGUAGE_DATA = "Silnik i dane językowe"
MODELS_INSTALLED = "zainstalowane"
MODELS_MISSING = "brak — tryb pełny jest niedostępny"
CHECKING = "Sprawdzanie…"
ENGINE_NOT_FOUND = "Nie znaleziono silnika OCR (Tesseract)."

SETTINGS_PROCESSING_TITLE = "Przetwarzanie"
DESKEW_OPTION = "Prostowanie (deskew)"
DESKEW_OPTION_TIP = "Wykrywa i usuwa przekrzywienie skanu"
DENOISE_OPTION = "Usuwanie szumów"
DENOISE_OPTION_TIP = (
    "Usuwa kropki i ziarno; silniejszy filtr włącza się tylko przy zaszumionych skanach"
)
CONTRAST_OPTION = "Poprawa kontrastu"
CONTRAST_OPTION_TIP = "Rozciąga jasność wyblakłych skanów"
PDF_DPI = "Rozdzielczość renderowania PDF"
PDF_DPI_TIP = "300 dpi to dobry kompromis. Wyższa rozdzielczość pomaga przy drobnym druku, ale jest wolniejsza."
THREADS = "Liczba wątków"
THREADS_AUTO = "Automatycznie"
THREADS_TIP = "Ile stron może być rozpoznawanych jednocześnie. „Automatycznie” zostawia jeden rdzeń wolny dla interfejsu."

SETTINGS_OUTPUT_TITLE = "Wyjście"
OUTPUT_ASK = "Pytaj o miejsce zapisu za każdym razem"
OUTPUT_FOLDER = "Zapisuj zawsze do folderu:"
NO_FOLDER = "Nie wybrano folderu"
CHOOSE_FOLDER = "Wybierz…"
RESET_DEFAULT = "Domyślny"
NAME_PATTERN = "Schemat nazwy pliku"
NAME_PATTERN_TIP = (
    "{nazwa} zostanie zastąpione nazwą pliku źródłowego, np. {nazwa}_ocr → umowa_ocr.docx"
)
NAME_PATTERN_INVALID = "Schemat nazwy pliku musi zawierać {nazwa}."
OUTPUT_FOLDER_MISSING = (
    "Wybierz folder wyjściowy albo zaznacz „Pytaj o miejsce zapisu za każdym razem”."
)
DEFAULT_FORMAT = "Domyślny format zapisu"
TEMP_FOLDER = "Folder tymczasowy"
CLIPBOARD_CLEAR = "Czyść schowek po"
NEVER = "nigdy"
CLIPBOARD_NOTE = (
    "Aplikacja wyczyści schowek tylko wtedy, gdy nadal zawiera skopiowany z niej tekst. "
    "Menedżery schowka (np. historia schowka w Windows) mogą przechowywać własną kopię."
)

SETTINGS_APPEARANCE_TITLE = "Wygląd"
THEME = "Motyw"
THEME_LABELS: dict[str, str] = {"system": "Systemowy", "light": "Jasny", "dark": "Ciemny"}
FONT_SIZE = "Rozmiar czcionki"
SYSTEM_DEFAULT = "systemowy"
UI_LANGUAGE = "Język interfejsu"
UI_LANGUAGE_TIP = "Kolejne języki interfejsu mogą zostać dodane w przyszłości."

SETTINGS_ADVANCED_TITLE = "Zaawansowane"
LOG_LEVEL = "Poziom logowania"
LOG_LEVELS: dict[str, str] = {
    "warning": "Tylko ostrzeżenia i błędy",
    "info": "Informacje",
    "debug": "Szczegółowy (diagnostyka)",
}
LOG_LEVEL_TIP = "Logi pomagają diagnozować problemy techniczne."
LOG_NOTE = "Logi nigdy nie zawierają treści dokumentów ani nazw plików — tylko dane techniczne (liczba stron, czas, kody błędów)."
OPEN_LOG_FOLDER = "Otwórz folder logów"
CLEAR_TEMP = "Wyczyść pliki tymczasowe"
TEMP_CLEARED = "Pliki tymczasowe zostały usunięte."
RESTORE_DEFAULTS = "Przywróć ustawienia domyślne"
RESTORE_QUESTION = "Przywrócić wszystkie ustawienia do wartości domyślnych? Zmiany zostaną zapisane po kliknięciu OK."

NO_NETWORK_STATEMENT = "Aplikacja nie wykonuje połączeń sieciowych."
LICENSES = "Licencje komponentów"
LICENSES_MISSING = "Nie znaleziono pliku z licencjami dołączonego do aplikacji."
ENGINE_BANNER = "Nie znaleziono silnika OCR (Tesseract) lub danych językowych. Rozpoznawanie tekstu nie zadziała — zainstaluj aplikację ponownie."
CLIPBOARD_CLEARED = "Schowek został wyczyszczony."


def engine_status(version: str, langs: str) -> str:
    return f"{version}; dostępne języki: {langs}"


def missing_languages(langs: str) -> str:
    return f"Brak danych dla: {langs}"


def about_components(engine: str, models: str) -> str:
    return f"Silnik OCR: {engine}\nModele trybu pełnego: {models}"


def overwrite_question(name: str) -> str:
    return f"Plik „{name}” już istnieje w folderze wyjściowym. Zastąpić go?"


def minutes(n: int) -> str:
    return f"{n} min"
