# LokalOCR

Desktopowa aplikacja do OCR i konwersji dokumentów (PDF, PNG, JPG, TIFF → tekst, DOCX, PDF z warstwą tekstową, Markdown, HTML), działająca **wyłącznie offline**.

## Pobierz (Windows)

**[Pobierz najnowszą wersję](https://github.com/Szmok0/OCR_aplikacja/releases/latest)** — plik `LokalOCR-windows-basic.zip`: rozpakuj i uruchom `LokalOCR.exe`. Instrukcja: [`docs/install-windows.md`](docs/install-windows.md).

- Specyfikacja i zasady pracy: [`CLAUDE.md`](CLAUDE.md)
- Referencja UI: [`docs/ui-reference/ui-reference-v1.png`](docs/ui-reference/ui-reference-v1.png)
- Środowisko deweloperskie: [`docs/dev-setup.md`](docs/dev-setup.md)

## Uruchomienie

```bash
lokalocr-gui                              # okno aplikacji
```

Wymaga Tesseracta z danymi `pol` i `eng` (patrz [`docs/dev-setup.md`](docs/dev-setup.md)). Pakiet dla Windows (z dołączonym Tesseractem) buduje workflow `build-windows.yml`; instalacja: [`docs/install-windows.md`](docs/install-windows.md), kontrola offline: [`docs/offline-checklist.md`](docs/offline-checklist.md).

## Wiersz poleceń

```bash
lokalocr skan.pdf                         # wynik obok pliku: skan_ocr.txt
lokalocr skan.pdf -o wynik.txt            # konkretny plik wynikowy
lokalocr folder_ze_skanami -o wyniki/     # cały folder (-r: z podfolderami)
lokalocr cv.jpg -o - --layout original    # na standardowe wyjście, oryginalny układ
lokalocr --help
```

Kody wyjścia: `0` — wszystko przetworzone, `1` — część plików się nie udała, `2` — błędne wywołanie lub brak plików, `3` — brak Tesseracta albo danych językowych, `130` — przerwano (Ctrl+C).

Status: etap 7 — prototyp (pakiet Windows, autotest `--selftest`).

Licencje komponentów: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
