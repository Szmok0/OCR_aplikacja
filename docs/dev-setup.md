# Środowisko deweloperskie

Wymagany Python **3.12+**. Głównym systemem docelowym jest **Windows** (laptopy biurowe, CPU), testy działają też na Linuksie (środowisko chmurowe, CI).

## Instalacja

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pre-commit install
```

Linux / macOS:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pre-commit install
```

## Sprawdzenia (to samo co CI)

```bash
python scripts/check.py
```

Uruchamia kolejno: `ruff check`, `ruff format --check`, `mypy` (tryb strict), `pytest`, kontrolę licencji zależności (`scripts/check_licenses.py`).

## Zasady, o których łatwo zapomnieć

- Testy działają przy włączonym strażniku sieci (`lokalocr.netguard`, instalowany w `tests/conftest.py`). Test, który potrzebuje sieci, jest błędem.
- `LOKALOCR_ALLOW_NET=1` wyłącza strażnika — **tylko** dla skryptów deweloperskich (np. przyszłe `scripts/fetch_models.py`), nigdy w aplikacji ani w testach.
- Import `requests`, `httpx`, `urllib3`, `aiohttp`, `urllib.request`, `http.client` w `src/` blokuje ruff (`TID251`) i test `tests/test_banned_imports.py`.
- Nowa zależność uruchomieniowa: dopisz ją do `pyproject.toml` z przypiętą wersją, podaj licencję w PR. `scripts/check_licenses.py` odrzuci GPL/AGPL; LGPL jest dozwolone tylko dla PySide6/shiboken6.
- Testy wymagające modeli trybu pełnego oznaczaj `@pytest.mark.models`.
- Do repozytorium i sesji trafiają tylko dane syntetyczne (`scripts/make_fixtures.py`, etap 1).

## Tesseract (od etapu 1)

Tryb podstawowy wymaga Tesseracta 5 z danymi `pol` i `eng`.

Debian/Ubuntu:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng
```

Windows: instalator UB Mannheim (np. `choco install tesseract`) do `C:\Program Files\Tesseract-OCR`; jeśli brakuje `pol.traineddata`, skopiuj go do podfolderu `tessdata`. Aplikacja znajduje Tesseracta w tej kolejności: zmienna `LOKALOCR_TESSERACT` (ścieżka do pliku), kopia dołączona do aplikacji (folder `tesseract/` obok programu), `PATH`, domyślny folder instalacji w Windows. Folder danych językowych można wskazać zmienną `LOKALOCR_TESSDATA`.

Interfejs (PySide6) na Linuksie bez pulpitu potrzebuje jeszcze bibliotek systemowych Qt: `sudo apt-get install libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`. Testy UI działają w trybie `QT_QPA_PLATFORM=offscreen` (ustawianym automatycznie w `tests/conftest.py`).

Testy oznaczone `@pytest.mark.tesseract` są pomijane, jeśli Tesseracta nie ma. W CI ustawiamy `LOKALOCR_REQUIRE_TESSERACT=1`, żeby brak Tesseracta był błędem, a nie cichym pominięciem.

Tesseract jest uruchamiany z `OMP_THREAD_LIMIT=1`: wątki OpenMP w Tesseract aktywnie czekają, przez co kilka równoległych procesów potrafi zwolnić się nawzajem o rzędy wielkości, a jeden wątek jest szybszy nawet na bezczynnej maszynie.

## Dane testowe i jakość OCR

```bash
python scripts/make_fixtures.py               # zapisuje do tests/fixtures/generated/ (ignorowane przez git)
python scripts/measure_cer.py                 # CER/WER na zestawie syntetycznym
python scripts/measure_cer.py --compare       # porównanie wariantów obróbki obrazu
```

Wynik bazowy: [`docs/quality/cer-baseline.md`](quality/cer-baseline.md). Każda zmiana wpływająca na przetwarzanie powinna podać CER przed i po (§11).

## Tryb pełny (Docling)

Tryb pełny wymaga dodatkowych pakietów i modeli (ok. kilkaset MB):

```bash
# Linux: najpierw PyTorch w wersji CPU (bez bibliotek CUDA, które mają licencje własnościowe)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[full]"
python scripts/fetch_models.py           # pobiera modele do models/docling + MANIFEST.json
python scripts/fetch_models.py --verify  # sprawdza sumy SHA-256
```

Na Windows `pip install -e ".[full]"` instaluje PyTorch CPU z PyPI.

- `scripts/fetch_models.py` to **jedyne** miejsce z dostępem do sieci (§6.4); aplikacja czyta modele wyłącznie z `models/docling` (albo z folderu wskazanego zmienną `LOKALOCR_MODELS`).
- Aplikacja uznaje modele za dostępne tylko wtedy, gdy wszystkie pliki z `MANIFEST.json` istnieją i mają właściwy rozmiar; inaczej opcja „Pełny” jest wyszarzona.
- Docling działa w osobnym procesie (anulowanie = zakończenie procesu), z blokadą sieci i Tesseractem jako silnikiem OCR.
- Testy trybu pełnego: `pytest -m "docling or models"` (w CI osobne zadanie `full-mode`).
