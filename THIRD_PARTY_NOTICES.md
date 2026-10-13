# Komponenty zewnętrzne i licencje

LokalOCR korzysta z poniższych komponentów. Pełne teksty licencji dołączonych zasobów leżą obok nich w repozytorium (i w pakiecie aplikacji).

## Zasoby dołączone do aplikacji

| Komponent | Gdzie | Licencja | Tekst licencji |
|---|---|---|---|
| Ikony Lucide — lucide.dev (lucide-static 1.56.0; część wywodzi się z Feather, MIT) | `src/lokalocr/ui/resources/icons/*.svg` | ISC | `src/lokalocr/ui/resources/icons/LICENSE-lucide.txt` |
| Ikona aplikacji (zastępcza, własny projekt) | `src/lokalocr/ui/resources/app_icon.svg` | licencja projektu | — |

Ikony Lucide skopiowano bez zmian kształtu, z nazwami zgodnymi z konwencją z `CLAUDE.md` §7.8 (np. `status_ok.svg` = `circle-check`). Kolor jest podmieniany w czasie działania (`currentColor` → kolor motywu).

## Biblioteki uruchomieniowe (Python)

| Pakiet | Licencja | Uwagi |
|---|---|---|
| PySide6-Essentials, shiboken6 (Qt 6) | LGPL-3.0-only | linkowane dynamicznie (osobne biblioteki Qt w pakiecie, które można podmienić) |
| numpy | BSD-3-Clause (+ 0BSD, MIT, Zlib, CC0-1.0 w częściach) | |
| opencv-python-headless | Apache-2.0 | |
| Pillow | MIT-CMU | |
| pypdfium2 + PDFium | Apache-2.0 OR BSD-3-Clause; PDFium BSD-3-Clause | zależności PDFium (FreeType, libjpeg-turbo, libpng, zlib, lcms, OpenJPEG, ICU, abseil, agg, fast_float, simdutf, llvm-libc) — licencje permisywne, dołączone w pakiecie pypdfium2 |

Lista sprawdzana automatycznie: `python scripts/check_licenses.py`.

## Tryb pełny (pakiet „full”)

| Komponent | Licencja | Uwagi |
|---|---|---|
| Docling 2.138 (docling, docling-core, docling-parse, docling-ibm-models) | MIT | analiza struktury dokumentu |
| PyTorch, torchvision (CPU) | BSD-3-Clause (części: Apache-2.0, Apache-2.0 WITH LLVM-exception, BSL-1.0, MIT) | bez bibliotek CUDA |
| transformers, huggingface-hub, safetensors | Apache-2.0 | |
| pozostałe zależności trybu pełnego (~100 pakietów) | MIT / BSD / Apache-2.0 / MPL-2.0 / ISC / PSF / CNRI-Python | sprawdzane: `python scripts/check_licenses.py --extras full` |
| Model układu strony `docling-project/docling-layout-heron` | Apache-2.0 | wagi w `models/docling` |
| Model tabel TableFormer `docling-project/docling-models` | CDLA-Permissive-2.0 / Apache-2.0 | wagi w `models/docling` |

Licencje modeli odczytuje `python scripts/model_licenses.py` (z kart modeli; tylko w środowisku deweloperskim).

## Programy zewnętrzne

| Program | Licencja | Uwagi |
|---|---|---|
| Tesseract OCR 5 | Apache-2.0 | uruchamiany jako osobny proces; dane językowe `pol`, `eng` — Apache-2.0 |

## Tylko do testów (nie trafiają do aplikacji)

| Zasób | Licencja | Tekst licencji |
|---|---|---|
| Czcionki DejaVu (Sans, Sans Bold, Serif) | Bitstream Vera (permisywna), zmiany DejaVu w domenie publicznej | `tests/fixtures/fonts/LICENSE-DejaVu.txt` |
