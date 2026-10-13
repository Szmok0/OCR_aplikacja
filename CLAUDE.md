# LokalOCR — specyfikacja projektu i instrukcje dla agenta

> Nazwa robocza: **LokalOCR**. Aplikacja desktopowa do OCR i konwersji dokumentów, działająca **wyłącznie offline**.
> Ten plik jest jednocześnie specyfikacją (funkcje, architektura, UI) i zbiorem zasad dla agenta (Claude Code). Czytaj go w całości przed każdą większą zmianą.
> Referencja wizualna UI: `docs/ui-reference/ui-reference-v1.png` (patrz §7.1). Jeśli pliku nie ma w repozytorium, poproś właściciela o dodanie go przed etapem 3.

---

## 0. Zasady twarde (nie negocjuj ich, nawet jeśli wydaje się to wygodne)

1. **Zero ruchu sieciowego w aplikacji.** Kod aplikacji nigdy nie łączy się z internetem. Żadnej telemetrii, sprawdzania aktualizacji, raportów błędów, linków otwieranych w przeglądarce ani pobierania modeli w czasie działania. Pobieranie modeli robi osobny skrypt deweloperski (`scripts/fetch_models.py`), którego aplikacja nie zawiera.
2. **Dokumenty użytkownika są wrażliwe (RODO).** Nigdy nie loguj treści dokumentów ani rozpoznanego tekstu. Logi zawierają tylko metadane (rozmiar, liczba stron, czas, kod błędu), **bez nazw plików**.
3. **Dane testowe i przykłady w UI tylko syntetyczne lub fikcyjne.** Nie proś o prawdziwe dokumenty, nie wgrywaj ich do repozytorium ani do sesji. Dane z referencji UI (np. fikcyjne CV) służą wyłącznie jako makieta wyglądu. Fixtures generuje skrypt (§9).
4. **Zależności:** tylko licencje permisywne (MIT, BSD, Apache-2.0, MPL-2.0, ISC) oraz LGPL dla bibliotek dynamicznie linkowanych (PySide6). **Nie dodawaj** bibliotek GPL/AGPL (np. PyMuPDF, Surya/Marker) bez wyraźnej zgody właściciela. Przed dodaniem nowej zależności zapisz w PR jej licencję i powód.
5. **Małe PR-y.** Jeden etap z §10 = jeden lub kilka małych PR-ów. Nie łącz refaktoru z nową funkcją. Nie pushuj bezpośrednio do `main`.
6. **Nie zgaduj, sprawdzaj.** Biblioteki i ich API zmieniają się szybko. Przed użyciem Docling, Tesseract, PySide6 itd. sprawdź aktualną dokumentację i przypnij wersje w `pyproject.toml`.
7. **UI ma odpowiadać referencji (§7).** Odstępstwa są dozwolone tylko wtedy, gdy wynikają z zasad 0.1–0.3 lub z ograniczeń technicznych, i muszą być opisane w PR.
8. **Komunikaty dla użytkownika po polsku**, kod, nazwy i komentarze techniczne po angielsku.

---

## 1. Cel, zakres i scenariusze użycia

**Problem:** brakuje dobrej jakości OCR działającego offline. Dokumenty zawierają dane wrażliwe, więc usługi chmurowe nie wchodzą w grę.

**Kontekst projektu:** użytek osobisty jednego właściciela. Brak działu IT i firmowych polityk, a dane nie opuszczają aplikacji. Nie projektuj funkcji pod wdrożenia w organizacji (zarządzanie zgodami, centralna konfiguracja, podpisywanie pakietów na wymaganie IT).

**Minimum (tryb podstawowy):** czysty OCR + wynik do skopiowania lub zapisania jako plik.

**Maksimum (tryb pełny):** to samo + odtworzona struktura dokumentu (nagłówki, listy, tabele, obrazy), eksport do edytowalnego **DOCX** i wyciągnięcie obrazów do osobnego folderu.

### Scenariusze (akceptacyjne)
1. **CV (JPG/PDF)** → edytowalny tekst + opcjonalnie struktura (DOCX).
2. **Faktura, formularz** → tekst + tabele (DOCX/PDF).
3. **Skan umowy (wielostronicowy PDF)** → PDF z warstwą tekstową oraz tekst.
4. **Praca z danymi wrażliwymi** → brak połączeń sieciowych, widoczny znacznik offline, brak śladów dokumentów po zamknięciu aplikacji.

### Poza zakresem (v1)
Pismo odręczne (słaby punkt wszystkich otwartych narzędzi), wierne odwzorowanie wyglądu strony 1:1 (układ wielokolumnowy i pozycjonowanie mogą wymagać ręcznej poprawki), edycja bloków dokumentu w aplikacji (patrz §13), wykrywanie języka dokumentu, synchronizacja z chmurą.

**Języki dokumentów:** polski i angielski (pol+eng). Architektura ma pozwalać dodać kolejne.

---

## 2. Użytkownik i środowisko

- Pojedynczy użytkownik (właściciel) na własnym komputerze. Mimo to nie wymagaj uprawnień administratora ani instalacji sterowników czy usług, jeśli nie jest to konieczne (prostsza instalacja i mniejsze ryzyko).
- System docelowy: **do ustalenia** (§14). Projektuj wieloplatformowo (Windows, macOS, Linux); pierwszy pakiet budujemy dla systemu, który wskaże właściciel.
- Brak GPU nie może blokować pracy. Tryb podstawowy musi działać na samym CPU. GPU to opcjonalne przyspieszenie trybu pełnego.

---

## 3. Architektura

Przepływ danych jest liniowy i oparty na wspólnym modelu wyniku, żeby eksportery i UI były wspólne dla obu trybów:

```
Plik wejściowy (PDF / obraz / TIFF wielostronicowy)
   → Loader (strony jako obrazy)
   → Preprocess (prostowanie, odszumianie, kontrast)
   → Silnik (OCR podstawowy LUB analiza struktury)
   → DocumentModel (strony → bloki → linie, obrazy)
   → Eksportery (TXT, DOCX, PDF z warstwą tekstową, MD, HTML, folder obrazów)
```

### DocumentModel (neutralny, niezależny od silnika)
- `Document`: lista `Page`, metadane (liczba stron, język OCR, tryb, średnia pewność). **Bez nazwy pliku w logach.**
- `Page`: numer, rozmiar, lista `Block`.
- `Block`: `type` (`paragraph | heading | list_item | table | figure | caption`), `text`, `lines` (lista linii z pozycjami, potrzebna do widoku „Oryginalny układ"), `bbox` (X, Y, szerokość, wysokość), `confidence` (0–1 lub `None`, jeśli silnik nie podaje), `level` (dla nagłówków), `table` (siatka komórek, dla typu `table`), `image_ref` (dla `figure`).
- **Widok „Sekcje"** (potrzebny oknu struktury) jest wyliczany z bloków: nagłówek + kolejne bloki do następnego nagłówka tego samego lub wyższego poziomu. Nie jest przechowywany w modelu.
- Tryb podstawowy wypełnia bloki `paragraph` z liniami. Tryb pełny wypełnia wszystkie typy.

### Interfejsy silników (wymienialne)
```python
class OcrEngine(Protocol):
    def recognize(self, image: Image, lang: str) -> PageResult: ...

class StructureEngine(Protocol):
    def analyze(self, path: Path, lang: str) -> Document: ...
```
Nowy silnik = nowa klasa + wpis w rejestrze. UI i eksportery nie wiedzą, który silnik jest pod spodem.

### Pipeline i postęp
Pipeline emituje zdarzenia: `etap` (`loading | preprocessing | ocr | layout | export`), `strona`, `procent`, oraz możliwość anulowania. Szacowany czas pozostały liczony z ruchomej średniej czasu na stronę; dopóki nie ma danych, UI pokazuje „Szacowanie…".

---

## 4. Stack technologiczny (propozycja startowa)

| Obszar | Wybór | Uzasadnienie / uwagi |
|---|---|---|
| Język | Python 3.11+ | szybki rozwój, dojrzały ekosystem OCR |
| UI | **PySide6 (Qt 6)** | natywny wygląd, w pełni offline, drag & drop; LGPL — linkuj dynamicznie |
| OCR podstawowy | **Tesseract 5** (`pol`, `eng`) przez `pytesseract` lub `tesserocr` | Apache-2.0, CPU; binarka i dane językowe dołączane do instalatora; pewność na poziomie słów |
| Struktura (tryb pełny) | **Docling** (IBM) | MIT; układ, tabele, obrazy; **sprawdź w bieżącej dokumentacji**: tryb offline (`artifacts_path`), wybór silnika OCR (Tesseract), natywny eksport |
| Renderowanie PDF | **pypdfium2** | permisywna licencja; **nie używaj PyMuPDF (AGPL)** |
| Obróbka obrazu | Pillow + OpenCV (headless) | prostowanie, odszumianie, kontrast |
| DOCX | **python-docx** | MIT; składanie dokumentu z `DocumentModel` |
| PDF z warstwą tekstu | wyjście PDF z Tesseracta | unikamy OCRmyPDF/Ghostscript (AGPL) |
| Ikony UI | SVG z biblioteki o permisywnej licencji (np. Lucide — ISC, Tabler — MIT; **zweryfikuj licencję i dołącz jej tekst**) | skalowalne, kolorowane z motywu |
| Metryka jakości | `rapidfuzz` lub `jiwer` | CER/WER w testach |
| Testy | pytest, pytest-qt (`QT_QPA_PLATFORM=offscreen`) | |
| Jakość kodu | ruff, mypy, pre-commit | |
| Pakowanie | PyInstaller (one-folder) | etap 7 |

Jeśli któraś propozycja okaże się nieprzydatna (instalacja, licencja, jakość), zgłoś to w PR z uzasadnieniem i alternatywą zamiast po cichu ją zmieniać.

---

## 5. Tryby pracy

### Tryb podstawowy (zawsze dostępny)
- Loader → preprocess → Tesseract (pol+eng) → bloki `paragraph` z liniami.
- Wyjścia: tekst do skopiowania, **TXT**, **PDF z warstwą tekstową**, **DOCX** (same akapity), prosty **Markdown** i **HTML** (akapity).
- Brak dodatkowych modeli poza danymi Tesseracta. Musi działać na słabym komputerze.

### Tryb pełny (opcjonalny, wymaga dołączonych modeli)
- Docling (lokalne modele) → `DocumentModel` z nagłówkami, listami, tabelami i obrazami.
- Wyjścia: wszystko z trybu podstawowego + **DOCX ze strukturą** (nagłówki jako style `Heading 1–N`, prawdziwe tabele, obrazy osadzone), folder `obrazy/`, pełny **Markdown** i **HTML**, zakładka **Obrazy**, okno **Struktura dokumentu**.
- Jeśli modele nie są dostępne, aplikacja wyłącza opcję „Pełny" z jasnym wyjaśnieniem (podpowiedź przy opcji), a nie zgłasza błędu.
- Oczekiwania wobec DOCX: **czysty, edytowalny dokument**, nie kopia 1:1 wyglądu strony. Powiedz o tym użytkownikowi w opisie trybu.
- Opcja „Zachowaj strukturę (tryb pełny)" (§7.3, strefa 6) steruje zawartością eksportu: wyłączona = eksport jako czysty tekst (akapity) nawet w trybie pełnym.

---

## 6. Offline i prywatność (wymagania i weryfikacja)

### Wymagania
1. **Strażnik sieci (`netguard`)** uruchamiany przy starcie procesu: blokuje wszystkie połączenia poza pętlą zwrotną (podmiana `socket.socket.connect`, `socket.create_connection`, `socket.getaddrinfo`). Próba połączenia = wyjątek i wpis w logu (bez treści). Wyłączany wyłącznie zmienną `LOKALOCR_ALLOW_NET=1` w skryptach deweloperskich, nigdy w aplikacji.
2. Zmienne środowiskowe ustawiane na starcie: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` i odpowiedniki wymagane przez wybrane biblioteki (sprawdź dokumentację).
3. Zakaz importu bibliotek sieciowych w kodzie aplikacji (`requests`, `httpx`, `urllib3`, `aiohttp`) egzekwowany regułą ruff (`banned-api`) i testem.
4. Modele: tylko z lokalnego folderu `models/` dołączonego do instalatora. `scripts/fetch_models.py` pobiera je na maszynie z internetem, weryfikuje sumy kontrolne i zapisuje do `models/`.
5. **Żadnych śladów dokumentów po zamknięciu:** kolejka plików i miniatury istnieją tylko w pamięci albo w folderze tymczasowym sprzątanym po zamknięciu i przy starcie. Aplikacja **nie ma** listy „ostatnio otwarte", historii ani zapisanej kolejki. Pliki wynikowe zapisujemy tylko tam, gdzie wskaże użytkownik.
6. Schowek: kopiowanie tekstu to świadoma akcja użytkownika. W ustawieniach opcja „wyczyść schowek po X minutach" (domyślnie wyłączona) i krótka informacja, że menedżery schowka mogą zachować kopię.
7. Konfiguracja (plik w katalogu konfiguracyjnym użytkownika) nie zawiera nazw dokumentów ani ścieżek plików źródłowych (dozwolona ostatnio wybrana ścieżka folderu wyjściowego, jeśli użytkownik tego chce).
8. „Pomoc" i „O programie" korzystają wyłącznie z dokumentów dołączonych do aplikacji. Żadnych odnośników otwieranych w przeglądarce (adresy mogą występować jedynie jako zwykły, nieklikalny tekst).

### Weryfikacja (testy obowiązkowe)
- Test: próba połączenia z zewnętrznym adresem → wyjątek.
- Test: pełne przetworzenie przykładowego dokumentu przy aktywnym `netguard` kończy się sukcesem.
- Test: statyczne sprawdzenie, że w `src/` nie ma zakazanych importów.
- Test: po zamknięciu i sprzątaniu folder tymczasowy jest pusty.
- Ręcznie przed wydaniem: uruchomienie na maszynie bez sieci i przy zablokowanym ruchu wychodzącym w zaporze + obserwacja ruchu (`docs/offline-checklist.md` — krótka lista kroków dla właściciela).

---

## 7. UI / UX

### 7.1 Referencja i decyzje projektowe

Referencja: `docs/ui-reference/ui-reference-v1.png` (wersja 1.0 „projekt referencyjny"). Opisuje 9 elementów: okno główne ze strefami 1–6, okno struktury, ustawienia i okno postępu. **Przejmujemy układ, hierarchię i styl.** Poniżej decyzje tam, gdzie referencja jest niejednoznaczna albo koliduje z założeniami projektu:

| Temat | Referencja | Decyzja |
|---|---|---|
| Karty „Tekst / Podgląd / Obrazy" | Przy aktywnej karcie „Tekst" widać jednocześnie podgląd strony i tekst; znaczenie kart jest niejasne | **Karty przełączają widok obszaru roboczego:** *Tekst* = podział: podgląd oryginału + wynik tekstowy (domyślny); *Podgląd* = podgląd na całą szerokość z nakładką bloków; *Obrazy (N)* = galeria wyciągniętych obrazów (tryb pełny). |
| Struktura dokumentu | Osobne okno otwierane na żądanie | **Tak, osobne okno niemodalne**, otwierane przyciskiem „Struktura" przy kartach (aktywny w trybie pełnym). Nie jest kartą. |
| Okno postępu | „Opcjonalne — może być w głównym oknie" | **W v1 postęp jest w głównym oknie:** pasek w elemencie kolejki i w panelu wyniku. Osobne okno nie jest w v1 potrzebne. Rozwijane „Szczegóły" pokazuje etapy (bez treści dokumentu). |
| Pola w oknie struktury (Typ, Tekst, Poziom, współrzędne) | Wyglądają na edytowalne | **W v1 tylko do odczytu.** Edycja bloków jest w backlogu (§13). Trzy przełączniki przy współrzędnych zastępuje **jeden** przełącznik „Pokaż ramkę bloku w podglądzie". |
| „Język: polski (98%)" w pasku stanu | Sugeruje automatyczne wykrywanie języka | **Wykrywanie języka poza zakresem v1.** Pasek stanu pokazuje język OCR wybrany przez użytkownika i średnią **Pewność OCR** (jeśli silnik ją podaje, inaczej „—"). |
| Pasek tytułu | Własny, narysowany | **Natywna ramka okna systemu** + nagłówek aplikacji wewnątrz okna (lepsza dostępność i stabilność). |
| Ikony | Pliki PNG | **SVG** dla ikon UI (ostrość przy skalowaniu, kolor z motywu); PNG/ICO/ICNS tylko dla ikony aplikacji. |
| Prywatność | Nie dotyczy | Dodajemy: brak historii, brak linków zewnętrznych, nazwy plików nie trafiają do logów (§6). |

Dane na makiecie (CV „Jan Kowalski", zdjęcie, numery) są **fikcyjne** — nie kopiuj ich do testów ani do ustawień domyślnych.

### 7.2 Zasady ogólne
- Spokojny, nowoczesny wygląd, bez zbędnych ozdób. Ścieżka główna ma być oczywista: *przeciągnij plik → zobacz wynik → skopiuj albo zapisz*.
- **Brak okien przy starcie** (żadnych kreatorów, okien powitalnych ani zgód). Ewentualna jednorazowa podpowiedź — wbudowana w okno, nie modalna.
- Okna: **Główne** (do implementacji w pierwszej kolejności), **Struktura dokumentu** (na żądanie), **Ustawienia** (modalne), **Pomoc/O programie** (lokalne). Brak innych okien.
- Praca w tle: UI nigdy się nie zawiesza; przetwarzanie w osobnym wątku lub procesie, z możliwością anulowania.

### 7.3 Okno główne — strefy

Numeracja zgodna z referencją.

**Nagłówek (nad strefami).** Logo i nazwa „LokalOCR", podtytuł „OCR i konwersja dokumentów — w pełni offline". Po prawej: stały znacznik **„Offline — brak połączeń sieciowych"** (zielona kropka), przyciski **Ustawienia** i **Pomoc** (otwiera lokalną pomoc, §6.8).

**Strefa 1 — wczytywanie i kolejka (lewy panel, ok. 280 px).**
- Pole upuszczania z przerywaną obwódką: ikona pliku, „**Upuść pliki tutaj**", „PDF, PNG, JPG, TIFF", „lub kliknij, aby wybrać pliki", przycisk główny „**Wybierz pliki…**".
- Nagłówek „**Kolejka plików (N)**" i link „**Wyczyść**" (czyści kolejkę i folder tymczasowy).
- Element kolejki: miniatura, nazwa, liczba stron i rozmiar, status: **Gotowe** (zielona ikona), **Przetwarzanie… 65%** (pasek postępu), **Oczekuje** (ikona zegara), **Błąd** (czerwona ikona + krótki opis). Menu „⋯": *Pokaż wynik*, *Przetwórz ponownie*, *Usuń z kolejki*.
- Zaznaczony element ma jasne niebieskie tło; jego wynik widać w strefach 4–5. Domyślnie kolejka przetwarzana jest sekwencyjnie.

**Strefa 2 — szybkie ustawienia przetwarzania (pod kolejką).**
- „Język OCR": lista (Polski + Angielski (pol+eng), Polski, Angielski).
- „Tryb pracy": **Podstawowy** / **Pełny** (przełącznik radiowy; „Pełny" wyszarzony z podpowiedzią, jeśli brak modeli).
- „Automatyczna obróbka obrazu": przełącznik (szczegóły w ustawieniach).

**Strefa 3 — karty widoku:** *Tekst*, *Podgląd*, *Obrazy (N)* (zgodnie z §7.1). Karta *Obrazy* jest ukryta lub wyłączona w trybie podstawowym. Obok kart przycisk **„Struktura"** (tryb pełny).

**Strefa 4 — podgląd strony (środek).**
- Pasek narzędzi: poprzednia/następna strona, pole „1 / N", pomniejsz/powiększ i wartość „100%", dopasuj do okna, **rączka** (przesuwanie), **lupa**, **obrót w lewo/prawo**, **prostuj** (ręczne uruchomienie prostowania dla strony).
- Strona wyświetlana na ciemnoszarym tle; przewijanie i powiększanie myszą i gestami.
- W karcie *Podgląd* opcjonalna nakładka ramek bloków (po zaznaczeniu bloku w oknie struktury podświetla się jego ramka).

**Strefa 5 — wynik tekstowy (prawy panel).**
- Przełącznik: **„Oryginalny układ"** (zachowuje podział na linie i przybliżone położenie; czcionka równoszerokościowa) / **„Tekst uproszczony"** (scalone akapity).
- Pole „**Szukaj w tekście…**" z przyciskami następny/poprzedni wynik i podświetleniem trafień; menu „⋯" (np. zaznacz wszystko, zawijanie wierszy).
- Ikona kopiowania w rogu pola tekstu (kopiuje zawartość widocznego widoku).
- Pasek stanu pod tekstem: „**Strona 1 z N • Znaleziono 324 słowa • Język OCR: polski • Pewność OCR: 98%**" oraz przycisk główny „**Kopiuj tekst**".
- W czasie przetwarzania panel pokazuje pasek postępu, nazwę etapu („Rozpoznawanie tekstu (OCR)…", „Analiza układu…", „Eksport…"), „Szacowany czas: około N sekund" i przycisk „**Anuluj**" (czerwona obwódka).

**Strefa 6 — pasek akcji (dół).**
- Rozwijany przycisk główny „**Zapisz jako DOCX ▾**" (menu: DOCX, TXT, PDF z tekstem, Markdown, HTML).
- Przyciski szybkiego zapisu: **TXT**, **PDF (z tekstem)**, **Markdown**, **HTML**; oraz „**Otwórz folder z obrazami (N)**" (wyłączony w trybie podstawowym, z podpowiedzią).
- „Opcje wyniku (dla tego dokumentu)": pole **„Czysty tekst (zawsze)"** (zaznaczone, nieedytowalne) i **„Zachowaj strukturę (tryb pełny)"** (aktywne tylko w trybie pełnym; ikona informacji z krótkim wyjaśnieniem).
- Zapis: okno wyboru lokalizacji (lub domyślny folder wyjściowy z ustawień). Nazwa domyślna `<nazwa>_ocr.<rozszerzenie>`. Nigdy nie nadpisuj plików bez potwierdzenia. Po zapisie krótkie powiadomienie w oknie z akcją „Pokaż w folderze".

### 7.4 Okno „Struktura dokumentu" (tryb pełny, niemodalne)
- Tytuł: „Struktura dokumentu – <nazwa pliku>".
- **Lewy panel — drzewo:** Strona → Nagłówek, Akapit, **Sekcja: <tytuł>** (z zagnieżdżonymi akapitami, listami, tabelami), Obraz. Ikony typów, liczba elementów w nawiasie (np. „Akapit (2)", „Lista (4)").
- **Środek — „Podgląd bloku":** wycinek strony z zaznaczonym blokiem (obraz dla bloków typu obraz).
- **Prawy panel — „Właściwości bloku" (tylko do odczytu w v1):** Typ, Tekst, Poziom (np. H1), Współrzędne (X, Y, Szer., Wys.), przełącznik „Pokaż ramkę bloku w podglądzie", **Pewność rozpoznania** (pasek i wartość w %, a gdy brak danych: „—").
- Zaznaczenie bloku w drzewie przewija i podświetla go w głównym oknie.

### 7.5 Okno ustawień (modalne, panel kategorii po lewej)
- **OCR:** język domyślny, tryb domyślny, status modeli trybu pełnego (zainstalowane / brak) i danych językowych.
- **Przetwarzanie:** automatyczna obróbka obrazu (wł./wył.), przełączniki **Prostowanie (deskew)**, **Usuwanie szumów**, **Poprawa kontrastu**; rozdzielczość renderowania PDF (np. 200–300 dpi); liczba wątków (domyślnie auto).
- **Wyjście:** folder wyjściowy („pytaj za każdym razem" jako domyślne), schemat nazwy pliku, domyślny format zapisu, domyślnie „Zachowaj strukturę", folder tymczasowy, czyszczenie schowka po X minutach.
- **Wygląd:** motyw (jasny / ciemny / systemowy), rozmiar czcionki, język interfejsu (polski; struktura gotowa na kolejne).
- **Zaawansowane:** poziom logowania (logi bez treści i bez nazw plików), „Otwórz folder logów", „Wyczyść pliki tymczasowe", „Przywróć ustawienia domyślne". **Brak jakichkolwiek ustawień sieciowych i aktualizacji.**
- **O programie:** wersja, wersje silników i modeli, lista licencji komponentów (z dołączonych plików), informacja „Aplikacja nie wykonuje połączeń sieciowych".
- Zmiany zatwierdzane przyciskami OK/Anuluj albo zapisywane natychmiast (jedno z dwóch, spójnie dla całego okna).

### 7.6 Stany i komunikaty błędów
- **Pusty ekran:** czytelna zachęta w strefie 1 i w obszarze roboczym, wskazanie skrótu otwarcia pliku.
- **Przetwarzanie:** patrz strefy 1 i 5; możliwość anulowania; po anulowaniu element wraca do stanu „Oczekuje" lub jest usuwany (do wyboru przy anulowaniu).
- **Błędy** (komunikat po polsku + podpowiedź działania, bez śladu stosu w oknie; szczegóły techniczne tylko w logu, bez treści i bez nazw plików):

| Sytuacja | Komunikat (propozycja) |
|---|---|
| PDF chroniony hasłem | „Plik jest chroniony hasłem. Usuń zabezpieczenie i spróbuj ponownie." |
| Uszkodzony plik | „Nie udało się otworzyć pliku. Może być uszkodzony." |
| Nieobsługiwany format | „Ten format nie jest obsługiwany. Użyj PDF, PNG, JPG lub TIFF." |
| Brak modeli trybu pełnego | „Tryb pełny jest niedostępny: brak lokalnych modeli. Użyj trybu podstawowego." |
| Brak danych językowych | „Brak danych językowych dla wybranego języka." |
| Za mało pamięci / zbyt duży plik | „Plik jest zbyt duży do przetworzenia. Spróbuj niższej rozdzielczości." |
| Wynik pusty | „Nie znaleziono tekstu. Sprawdź jakość skanu lub język OCR." |

### 7.7 Styl wizualny i tokeny

Wartości kolorów **zmierzono orientacyjnie z referencji** (dopasuj po porównaniu ze zrzutem; trzymaj je w jednym pliku motywu, nigdy w kodzie widgetów).

| Token | Jasny (z referencji, orientacyjnie) | Ciemny (propozycja) | Zastosowanie |
|---|---|---|---|
| `accent` | `#0A64F5` (referencja ≈ `#0060F8`–`#0064FE`) | `#4C8DFF` | przycisk główny, aktywna karta, pasek postępu, przełączniki |
| `accent-soft` | `#DCECFE` | `#1B2B45` | zaznaczony element kolejki, tło aktywnych kontrolek |
| `success` | `#0ABB4B` | `#2FD36A` | znacznik offline, „Gotowe" |
| `danger` | `#F05058` | `#FF6B72` | „Anuluj", błędy |
| `bg` | `#FCFCFC` | `#16181D` | tło okna i paneli |
| `surface` | `#F6F6F6` | `#1E2127` | karty, pola |
| `border` | `#E4EAF0` | `#2C313A` | obwódki i separatory |
| `preview-bg` | `#3B3F46` | `#0F1115` | tło podglądu strony |
| `text` | `#1F2937` (propozycja) | `#E6E8EB` | tekst główny |
| `text-muted` | `#6B7280` (propozycja) | `#9AA1AB` | opisy pomocnicze |

- **Typografia:** czcionka systemowa interfejsu (żadnych czcionek z internetu). Nagłówek aplikacji ok. 20 px półgruby; tekst ok. 13 px; opisy 11–12 px. Wynik tekstowy w czcionce równoszerokościowej obsługującej polskie znaki (Consolas / SF Mono / DejaVu Sans Mono).
- **Kształty:** siatka 8 px, zaokrąglenia 8 px (przyciski, pola) i 10–12 px (karty), subtelne cienie, przełączniki w stylu „toggle", pola wyboru i opcje w kolorze `accent`.
- Jasny i ciemny motyw; kontrast zgodny z WCAG AA. Motyw „systemowy" podąża za ustawieniem systemu.

### 7.8 Ikony i zasoby graficzne

Ikony UI jako **SVG** w `src/lokalocr/ui/resources/icons/`, kolorowane z tokenów motywu. Nazwy zachowują konwencję z referencji. Ikona aplikacji: źródło SVG + wygenerowane PNG (m.in. 256 px), `.ico` i `.icns`. Na początek agent tworzy prosty **zastępczy projekt** ikony aplikacji (dokument z liniami tekstu na niebieskim tle, jak w referencji); właściciel może go podmienić na własny.

| Zasób | Zastosowanie |
|---|---|
| `app_icon_256` (+ `.ico`, `.icns`) | ikona aplikacji, nagłówek, okna |
| `file_pdf`, `file_image`, `file_docx` | typ pliku w kolejce; ikony formatów zapisu: `file_txt`, `file_markdown`, `file_html` |
| `status_ok`, `status_processing` (animowana), `status_error`, `status_wait` | statusy elementów kolejki |
| `btn_add` | dodawanie plików |
| `icon_settings`, `icon_help`, `icon_offline` | nagłówek i znacznik offline |
| `icon_copy`, `icon_search`, `icon_more`, `icon_info`, `icon_close`, `icon_check`, `icon_clear` | ogólne akcje |
| `icon_prev`, `icon_next`, `icon_zoom_in`, `icon_zoom_out`, `icon_fit`, `icon_hand`, `icon_magnifier`, `icon_rotate_left`, `icon_rotate_right`, `icon_deskew` | pasek narzędzi podglądu |
| `icon_save`, `icon_folder_open` | zapis i otwarcie folderu obrazów |
| `icon_tab_text`, `icon_tab_preview`, `icon_tab_images`, `icon_structure` | karty i przycisk struktury |
| `node_page`, `node_heading`, `node_paragraph`, `node_section`, `node_list`, `node_table`, `node_image` | drzewo struktury |

W `THIRD_PARTY_NOTICES.md` zapisz źródło i licencję ikon (z dołączonym tekstem licencji).

### 7.9 Skróty i dostępność
- Skróty: `Ctrl+O` otwórz, `Ctrl+S` zapisz (domyślny format), `Ctrl+C` kopiuj wynik (gdy fokus na tekście), `Ctrl+F` szukaj w tekście, `Ctrl+,` ustawienia, `F1` pomoc, `Esc` anuluj, `Delete` usuń z kolejki.
- Pełna nawigacja klawiaturą, widoczny fokus, podpowiedzi (tooltips) dla ikon, skalowanie czcionki zgodnie z ustawieniem systemu i skalowaniem DPI.

### 7.10 Teksty interfejsu
Wszystkie napisy w jednym module (`ui/strings_pl.py` lub `tr()`), aby łatwo dodać inny język. Teksty z referencji (polskie) są wiążące, o ile nie kolidują z §6: „Upuść pliki tutaj", „Wybierz pliki…", „Kolejka plików", „Wyczyść", „Gotowe", „Oczekuje", „Przetwarzanie…", „Ustawienia szybkiego przetwarzania", „Język OCR", „Tryb pracy", „Podstawowy", „Pełny", „Automatyczna obróbka obrazu", „Tekst", „Podgląd", „Obrazy", „Oryginalny układ", „Tekst uproszczony", „Szukaj w tekście…", „Kopiuj tekst", „Zapisz jako DOCX", „Otwórz folder z obrazami", „Czysty tekst (zawsze)", „Zachowaj strukturę (tryb pełny)", „Struktura dokumentu", „Właściwości bloku", „Pewność rozpoznania", „Anuluj", „Szczegóły".

### 7.11 Wskazówki implementacyjne (Qt)
- Okno główne: `QMainWindow`; trzy kolumny w `QSplitter` (kolejka | podgląd | wynik); karty widoku przez `QStackedWidget`/`QTabBar`.
- Kolejka: `QListView` z własnym delegatem (miniatura, status, pasek postępu).
- Podgląd: `QGraphicsView` + `QGraphicsPixmapItem`, nakładka ramek bloków jako elementy sceny; zoom i przesuwanie w widoku.
- Wynik tekstowy: `QPlainTextEdit` (tylko do odczytu) z podświetleniem wyników wyszukiwania.
- Struktura: `QTreeView` z modelem wyliczanym z `DocumentModel` (§3).
- Ustawienia: `QDialog` z `QListWidget` kategorii i `QStackedWidget`.
- Motyw: generowany z tokenów (QSS + `QPalette`); przełączanie jasny/ciemny bez restartu.
- Praca w tle: wątek roboczy lub oddzielny proces z komunikacją przez sygnały; anulowanie musi przerywać pracę w rozsądnym czasie.
- Przekazywanie danych między UI a pipeline tylko przez `DocumentModel` i zdarzenia postępu (§3).

---

## 8. Struktura repozytorium

```
lokalocr/
├── CLAUDE.md                  # ten plik
├── pyproject.toml             # przypięte wersje, ruff/mypy/pytest
├── src/lokalocr/
│   ├── netguard.py            # blokada sieci (§6)
│   ├── config.py
│   ├── model.py               # DocumentModel (+ widok sekcji)
│   ├── loader.py              # PDF/obrazy → strony
│   ├── preprocess.py
│   ├── engines/
│   │   ├── base.py            # OcrEngine, StructureEngine
│   │   ├── tesseract.py
│   │   └── docling_engine.py
│   ├── exporters/
│   │   ├── txt.py  docx.py  pdf_text.py  markdown.py  html.py  images.py
│   ├── pipeline.py            # etapy, postęp, anulowanie
│   ├── cli.py                 # wiersz poleceń (testy, automatyzacja)
│   └── ui/
│       ├── app.py  main_window.py  structure_window.py  settings_dialog.py
│       ├── theme.py  strings_pl.py  widgets/
│       └── resources/ (icons/, app icon)
├── scripts/
│   ├── fetch_models.py        # jedyne miejsce z dostępem do sieci (dev)
│   └── make_fixtures.py       # syntetyczne dokumenty testowe
├── tests/
├── docs/
│   ├── ui-reference/ui-reference-v1.png
│   ├── offline-checklist.md
│   ├── dev-setup.md
│   └── user-guide.md          # dołączany do aplikacji jako lokalna pomoc
└── (CI i szablon PR zależnie od platformy git)
```

---

## 9. Środowisko deweloperskie w chmurze i dane testowe

Pracujemy w chmurowym środowisku Claude Code z podpiętym repozytorium właściciela.

- **Do sesji trafia wyłącznie kod.** Żadnych prawdziwych dokumentów, danych osobowych ani zrzutów z pracy.
- Środowisko chmurowe może mieć ograniczony dostęp do sieci. Testy wymagające dużych modeli oznacz `@pytest.mark.models` i traktuj jako opcjonalne; pełne testy modeli właściciel uruchamia lokalnie.
- Zależności systemowe w środowisku testowym (Debian/Ubuntu, przykład): `tesseract-ocr`, `tesseract-ocr-pol`, `tesseract-ocr-eng`. Zapisz kroki w `docs/dev-setup.md`.
- Testy UI: `QT_QPA_PLATFORM=offscreen` + pytest-qt. Zrzuty ekranu okien do przeglądu przez właściciela generuj w trybie offscreen na danych fikcyjnych.

### Dane testowe (`make_fixtures.py`)
- Strony z tekstem polskim z pełnym zestawem diakrytyków (np. „Zażółć gęślą jaźń"), czcionki z obsługą polskich znaków.
- Warianty: czysty skan, obrót o kilka stopni, szum, niski kontrast, 150 / 200 / 300 dpi.
- Typy dokumentów zgodne ze scenariuszami z §1: CV (nagłówki, listy, zdjęcie), faktura (tabela), wielostronicowy skan umowy.
- Znany tekst wzorcowy → liczymy **CER/WER** i zapisujemy wynik bazowy. Progi ustalamy po pierwszych pomiarach.

---

## 10. Plan prac (etapy = małe PR-y, każdy z kryteriami akceptacji)

**Etap 0 — Szkielet.** Repozytorium startuje jako puste: pierwszy commit (robi właściciel) zawiera tylko `CLAUDE.md` i `docs/ui-reference/ui-reference-v1.png`. Dalsza praca w Claude Code z dostępem do tego repozytorium. Struktura repo, `pyproject.toml`, ruff/mypy/pytest, CI, `netguard` + testy z §6, reguła zakazu importów sieciowych, dodanie referencji UI do `docs/ui-reference/`.
*Akceptacja:* CI zielone, test blokady sieci przechodzi.

**Etap 1 — Rdzeń podstawowy.** `loader` (PDF przez pypdfium2, PNG/JPG, wielostronicowy TIFF), `preprocess`, `engines/tesseract` (z liniami i pewnością), `DocumentModel`, eksport TXT, `make_fixtures.py`.
*Akceptacja:* dokument syntetyczny → poprawny tekst, zapisany pomiar CER.

**Etap 2 — CLI.** `lokalocr plik -o wynik --mode basic --lang pol+eng`.
*Akceptacja:* przetwarzanie wsadowe folderu, kody wyjścia, test przy aktywnym `netguard`.

**Etap 3 — Okno główne, szkielet.** Nagłówek ze znacznikiem offline, strefa 1 (upuszczanie, kolejka, statusy, menu elementu), strefa 2, strefa 5 (widoki tekstu, wyszukiwanie, „Kopiuj tekst", pasek stanu), zapis TXT, praca w tle z anulowaniem, postęp w kolejce i panelu wyniku.
*Akceptacja:* testy pytest-qt; UI nie blokuje się przy dużym PDF; po zamknięciu brak śladów w folderze tymczasowym.

**Etap 4 — Podgląd i eksport podstawowy.** Strefa 3 (karty), strefa 4 (podgląd z zoomem, obrotem, prostowaniem), strefa 6 (zapis DOCX z akapitów, PDF z warstwą tekstową, Markdown, HTML), opcje wyniku.
*Akceptacja:* pliki otwierają się w Word/LibreOffice; tekst w PDF da się zaznaczać i wyszukiwać.

**Etap 5 — Ustawienia, motywy, dopracowanie.** Okno ustawień (wszystkie kategorie), motywy jasny/ciemny z tokenów (§7.7), ikony SVG (§7.8), stany błędów (§7.6), skróty i dostępność (§7.9), lokalna pomoc i „O programie".
*Akceptacja:* przegląd zrzutów ekranu przez właściciela względem referencji, kontrast AA.

**Etap 6 — Tryb pełny.** `docling_engine` z lokalnymi modelami, mapowanie do `DocumentModel`, DOCX ze strukturą (style nagłówków, tabele, obrazy), folder `obrazy/`, pełny Markdown/HTML, karta *Obrazy*, okno *Struktura dokumentu* (tylko do odczytu). Włącz generowanie obrazów obiektów w Docling. Jeśli bieżąca wersja ma natywny eksport DOCX, porównaj jakość z własnym eksporterem i wybierz lepszy.
*Akceptacja:* dokument z tabelą, listą i obrazem → DOCX z odpowiednimi elementami; działa przy aktywnym `netguard`.

**Etap 7 — Pakowanie i dokumentacja.** PyInstaller (one-folder) z dołączonym Tesseractem, danymi `pol`/`eng` i folderem `models/`, instrukcja instalacji offline, `docs/offline-checklist.md`, `docs/user-guide.md`. Pakiety PyInstaller bywają oznaczane przez antywirusy (fałszywe alarmy); podpisanie kodu jest opcjonalne i nie jest wymagane do użytku osobistego.
*Akceptacja:* instalacja na czystej maszynie bez sieci, ręczny test z §6 wykonany.

**Etap 8+ — Rozszerzenia** (§13).

---

## 11. Jakość i definicja ukończenia

- Każdy PR: testy dla nowego kodu, `ruff` i `mypy` bez błędów, opis zmian, informacja o nowych zależnościach i ich licencjach, w razie zmian w UI zrzuty ekranu (dane fikcyjne).
- Obowiązkowe w CI: test blokady sieci, test zakazanych importów, kontrola licencji zależności (np. `pip-licenses`) z listą dozwolonych.
- Zmiana wpływająca na przetwarzanie: porównanie CER przed/po na zestawie syntetycznym.
- „Gotowe" = działa, jest przetestowane, ma dokumentację użytkownika, jest zgodne z referencją UI (lub odstępstwo jest opisane) i nie narusza żadnej zasady z §0.

---

## 12. Workflow git

- Gałęzie: `main` (stabilna, chroniona), `feat/<etap>-<krótki-opis>`, `fix/<opis>`.
- Commity w stylu Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- Szablon PR: *co i dlaczego*, *jak przetestowano*, *nowe zależności i licencje*, *wpływ na prywatność/offline*, *zgodność z referencją UI*.
- Agent tworzy PR i **nie scala go sam**. Scalanie po przeglądzie właściciela.
- W razie niepewności co do architektury, licencji lub UI agent otwiera dyskusję/zgłoszenie zamiast zgadywać.

---

## 13. Rozszerzenia na później (backlog)

Architektura (interfejsy silników, wspólny `DocumentModel`) ma ułatwiać dodawanie funkcji bez przebudowy:

- **Edycja bloków w oknie struktury** (zmiana typu, poziomu nagłówka, tekstu, z cofaniem) przed eksportem — pola istnieją już w układzie okna (tylko do odczytu w v1).
- **Anonimizacja i maskowanie danych osobowych** (np. PESEL z kontrolą sumy, NIP, numery kont, e-maile) z podglądem przed zapisem. Szczególnie przydatne przy RODO.
- **Wykrywanie języka dokumentu** (lokalna biblioteka o permisywnej licencji) i pokazywanie go w pasku stanu.
- Eksport tabel do **XLSX/CSV**.
- „Zapisz wszystko" dla całej kolejki i obserwowanie katalogu.
- Osobne okno postępu dla długich zadań wsadowych (jak w referencji, element 9).
- Lokalny, szyfrowany indeks przetworzonych dokumentów z wyszukiwaniem.
- Dodatkowe silniki OCR (np. PaddleOCR, docTR) jako wymienne moduły — po sprawdzeniu licencji i jakości dla polskiego.
- Lokalny model wizyjno-językowy do trudnych stron (opcjonalnie, wymaga GPU).
- Porównywanie dwóch wersji dokumentu, dodatkowe języki interfejsu i OCR.

Każde rozszerzenie zaczyna się od krótkiej notatki w `docs/` (cel, ryzyko, licencje, wpływ na offline) i osobnego PR-a.

---

## 14. Otwarte pytania i rzeczy do zweryfikowania

**Do ustalenia z właścicielem:**
- System docelowy (Windows / macOS / Linux) i czy komputer ma kartę graficzną.
- Gdzie będzie hostowane repozytorium (np. GitHub) — od tego zależy konfiguracja CI i budowania pakietu. Dopóki nie wiadomo, nie dodawaj plików CI specyficznych dla platformy; przygotuj uruchamianie testów i lintu jako lokalne polecenia (np. `make check` lub skrypt).
- Czy zastępczy projekt ikony aplikacji wystarczy, czy właściciel dostarczy własny.

**Do sprawdzenia w bieżącej dokumentacji przez agenta (nie zakładaj):**
- Docling: praca offline z lokalnymi modelami, wybór Tesseracta jako silnika OCR, dostępność natywnego eksportu DOCX w bieżącej wersji.
- Licencje wag modeli używanych przez Docling oraz danych językowych Tesseracta.
- Najlepszy sposób dołączenia binarki Tesseracta do pakietu na docelowym systemie.
- Licencja wybranej biblioteki ikon i obowiązek dołączenia jej tekstu.
- Czy polskie dokumenty z diakrytykami osiągają akceptowalny CER w trybie podstawowym; jeśli nie, zaproponuj ulepszenia obróbki obrazu lub alternatywny silnik (z analizą licencji).

**Ograniczenia, o których trzeba pamiętać:**
- Pismo odręczne nie jest wspierane w v1.
- Wyniki z publicznych porównań dotyczą głównie angielskiego; jakość polską trzeba zmierzyć na dokumentach syntetycznych, a potem sprawdzić lokalnie na dokumentach właściciela.
- Przetwarzanie lokalne zmniejsza ryzyko, ale samo nie gwarantuje zgodności z RODO. Zgodność zależy od tego, czyje dane i w jakim celu są przetwarzane; ocena należy do właściciela (to nie jest porada prawna).
