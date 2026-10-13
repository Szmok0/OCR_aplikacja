# Jakość OCR — pomiar bazowy (etap 1)

Pomiar na syntetycznym zestawie z `scripts/make_fixtures.py` (dane fikcyjne, §9): CV z nagłówkami i listą, faktura z tabelą, trzystronicowa umowa (skan jako PDF z obrazami). Każdy dokument w rozdzielczości 150 / 200 / 300 dpi i w czterech wariantach: `clean`, `rotated` (obrót o 3°), `noisy` (szum gaussowski σ=28 + sól i pieprz), `lowcontrast` (zakres jasności 105–190).

- **CER** — odległość Levenshteina na znakach / długość tekstu wzorcowego, po scaleniu białych znaków i usunięciu znaków punktorów.
- **WER** — to samo na słowach. Jest wyższy, bo jeden błędny znak psuje całe słowo, a kolejność czytania dwóch kolumn (np. sprzedawca/nabywca na fakturze) też się tu liczy.
- Czas: jeden rdzeń kontenera CI, Tesseract z `OMP_THREAD_LIMIT=1`. Na laptopie biurowym będzie podobnie lub szybciej.

Odtworzenie: `python scripts/measure_cer.py` (tabela) i `python scripts/measure_cer.py --compare` (warianty obróbki).

## Wybór domyślnej obróbki obrazu

Średni i najgorszy CER dla 36 kombinacji (dokument × dpi × wariant):

- **brak obróbki**: średni CER 3.53%, najgorszy 32.92% (invoice/300/rotated), 1.3 s/strona
- **tylko skalowanie**: średni CER 7.11%, najgorszy 58.93% (invoice/150/noisy), 1.6 s/strona
- **bez odszumiania**: średni CER 5.26%, najgorszy 59.72% (invoice/150/noisy), 1.9 s/strona
- **bez prostowania**: średni CER 3.17%, najgorszy 27.90% (invoice/300/rotated), 1.9 s/strona
- **bez kontrastu**: średni CER 1.34%, najgorszy 2.45% (cv/150/noisy), 1.8 s/strona
- **domyślne**: średni CER 1.32%, najgorszy 2.77% (contract/150/noisy), 1.9 s/strona

Wnioski:
- **Prostowanie** jest kluczowe: bez niego obrócony skan faktury ma CER 28–33%.
- **Usuwanie szumów** jest kluczowe dla zaszumionych skanów w niskiej rozdzielczości (bez niego do 60% CER). Kosztowny filtr non-local means (~2 s/stronę) uruchamia się tylko wtedy, gdy szacowany poziom szumu przekracza próg, więc czyste skany nic nie tracą.
- **Samo skalowanie** w górę (150 → 300 dpi) bez odszumiania pogarsza wynik, bo wzmacnia szum. W zestawie domyślnym działa dobrze.
- **Poprawa kontrastu** prawie nie zmienia CER na tym zestawie (1,34% → 1,32%), ale jest tania (~0,05 s), więc zostaje włączona, z myślą o wyblakłych skanach.

Domyślnie wszystkie kroki są włączone (`PreprocessOptions()`).

## Wynik bazowy (ustawienia domyślne, `pol+eng`)


| Dokument | DPI | Wariant | CER | WER | s/strona |
|---|---|---|---|---|---|
| cv | 150 | clean | 1.78% | 7.89% | 1.7 |
| cv | 150 | rotated | 1.56% | 6.14% | 1.5 |
| cv | 150 | noisy | 1.67% | 7.89% | 2.2 |
| cv | 150 | lowcontrast | 1.78% | 7.89% | 1.5 |
| cv | 200 | clean | 1.45% | 6.14% | 1.4 |
| cv | 200 | rotated | 1.67% | 7.02% | 1.7 |
| cv | 200 | noisy | 1.89% | 7.89% | 2.2 |
| cv | 200 | lowcontrast | 1.67% | 7.02% | 1.5 |
| cv | 300 | clean | 1.67% | 7.02% | 1.5 |
| cv | 300 | rotated | 1.67% | 7.02% | 1.7 |
| cv | 300 | noisy | 1.67% | 7.02% | 4.0 |
| cv | 300 | lowcontrast | 1.67% | 7.02% | 1.5 |
| invoice | 150 | clean | 1.10% | 5.94% | 1.1 |
| invoice | 150 | rotated | 1.10% | 5.94% | 1.5 |
| invoice | 150 | noisy | 1.10% | 3.96% | 1.4 |
| invoice | 150 | lowcontrast | 1.10% | 5.94% | 1.1 |
| invoice | 200 | clean | 1.10% | 5.94% | 1.2 |
| invoice | 200 | rotated | 0.78% | 3.96% | 1.4 |
| invoice | 200 | noisy | 1.57% | 7.92% | 1.8 |
| invoice | 200 | lowcontrast | 1.10% | 5.94% | 1.3 |
| invoice | 300 | clean | 2.19% | 10.89% | 1.2 |
| invoice | 300 | rotated | 1.88% | 8.91% | 1.3 |
| invoice | 300 | noisy | 1.72% | 7.92% | 3.5 |
| invoice | 300 | lowcontrast | 2.19% | 10.89% | 1.2 |
| contract | 150 | clean | 0.48% | 5.34% | 2.7 |
| contract | 150 | rotated | 0.48% | 5.59% | 2.7 |
| contract | 150 | noisy | 2.77% | 10.17% | 2.9 |
| contract | 150 | lowcontrast | 0.48% | 5.34% | 2.7 |
| contract | 200 | clean | 0.65% | 5.97% | 2.2 |
| contract | 200 | rotated | 0.58% | 4.91% | 2.4 |
| contract | 200 | noisy | 0.85% | 6.90% | 2.9 |
| contract | 200 | lowcontrast | 0.85% | 6.90% | 2.3 |
| contract | 300 | clean | 1.05% | 8.01% | 2.3 |
| contract | 300 | rotated | 0.67% | 5.34% | 2.7 |
| contract | 300 | noisy | 0.93% | 7.24% | 4.5 |
| contract | 300 | lowcontrast | 0.76% | 5.59% | 2.2 |
| **średnio** | | | **1.32%** | | |

Wniosek: tryb podstawowy osiąga **CER ok. 1–3%** na polskich dokumentach z pełnym zestawem znaków diakrytycznych, także przy obrocie, szumie i słabym kontraście. Pozostałe błędy to głównie punktory (`•` → `e`), separatory tabel (`|`) i kolejność czytania kolumn.

Testy (`tests/test_tesseract.py`, `tests/test_pipeline.py`, `tests/test_quality.py`) pilnują progów z zapasem względem tych wartości.
