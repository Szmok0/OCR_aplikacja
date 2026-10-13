# LokalOCR

Desktopowa aplikacja do OCR i konwersji dokumentów (PDF, PNG, JPG, TIFF → tekst, DOCX, PDF z warstwą tekstową, Markdown, HTML), działająca **wyłącznie offline**.

- Specyfikacja i zasady pracy: [`CLAUDE.md`](CLAUDE.md)
- Referencja UI: [`docs/ui-reference/ui-reference-v1.png`](docs/ui-reference/ui-reference-v1.png)
- Środowisko deweloperskie: [`docs/dev-setup.md`](docs/dev-setup.md)

## Wiersz poleceń

```bash
lokalocr skan.pdf                         # wynik obok pliku: skan_ocr.txt
lokalocr skan.pdf -o wynik.txt            # konkretny plik wynikowy
lokalocr folder_ze_skanami -o wyniki/     # cały folder (-r: z podfolderami)
lokalocr cv.jpg -o - --layout original    # na standardowe wyjście, oryginalny układ
lokalocr --help
```

Kody wyjścia: `0` — wszystko przetworzone, `1` — część plików się nie udała, `2` — błędne wywołanie lub brak plików, `3` — brak Tesseracta albo danych językowych, `130` — przerwano (Ctrl+C).

Status: etap 2 (rdzeń OCR + wiersz poleceń).
