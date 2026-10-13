# Środowisko deweloperskie

Wymagany Python **3.11+**. Głównym systemem docelowym jest **Windows** (laptopy biurowe, CPU), testy działają też na Linuksie (środowisko chmurowe, CI).

## Instalacja

Windows (PowerShell):

```powershell
py -3.11 -m venv .venv
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

## Zależności systemowe (od etapu 1)

Debian/Ubuntu:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng
```

Windows: sposób dołączenia Tesseracta do instalatora ustalimy w etapie 7; na czas rozwoju wystarczy instalacja Tesseracta 5 z danymi `pol` i `eng` oraz wpis w `PATH`. Szczegóły dopiszemy w etapie 1.
