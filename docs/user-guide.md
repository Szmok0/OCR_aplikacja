# LokalOCR — pomoc

LokalOCR rozpoznaje tekst w skanach i zdjęciach dokumentów i zapisuje go jako TXT, DOCX, PDF z warstwą tekstową, Markdown lub HTML. **Wszystko dzieje się na tym komputerze — aplikacja nie łączy się z internetem.**

## Szybki start

1. **Dodaj pliki** — przeciągnij je do okna albo kliknij **Wybierz pliki…** (Ctrl+O). Obsługiwane formaty: PDF, PNG, JPG, TIFF (także wielostronicowy). Możesz też przeciągnąć cały folder.
2. **Poczekaj na wynik** — pliki są przetwarzane po kolei. Postęp widać w kolejce i w prawym panelu. Przetwarzanie można przerwać przyciskiem **Anuluj** (Esc).
3. **Skopiuj lub zapisz** — **Kopiuj tekst** kopiuje widoczny tekst do schowka, a przyciski na dole zapisują wynik do pliku. Ctrl+S zapisuje w domyślnym formacie (DOCX).

## Okno główne

- **Kolejka plików** (lewa kolumna) — status każdego pliku: *Oczekuje*, *Przetwarzanie…*, *Gotowe* albo krótki opis błędu. Menu **⋯** przy pliku: *Pokaż wynik*, *Przetwórz ponownie*, *Usuń z kolejki*. **Wyczyść** usuwa wszystkie pliki z kolejki.
- **Ustawienia szybkiego przetwarzania** — język dokumentu, tryb pracy i automatyczna obróbka obrazu. Zmiany dotyczą kolejnych plików; aby zastosować je do pliku już przetworzonego, wybierz *Przetwórz ponownie*.
- **Karty** nad podglądem:
  - *Tekst* — podgląd oryginału obok rozpoznanego tekstu,
  - *Podgląd* — strona na całą szerokość z ramkami rozpoznanych fragmentów,
  - *Obrazy* — obrazy wyciągnięte z dokumentu (tryb pełny).
- **Podgląd strony** — przewijanie stron (PgUp/PgDn), powiększanie (Ctrl+kółko myszy, gest szczypania), dopasowanie do okna, rączka do przesuwania, lupa (kliknięcie powiększa, prawy przycisk pomniejsza), obrót i **prostowanie** krzywo zeskanowanej strony.
- **Wynik tekstowy** (prawa kolumna):
  - *Oryginalny układ* zachowuje podział na linie i przybliżone położenie tekstu,
  - *Tekst uproszczony* łączy linie w akapity — wygodny do dalszej edycji,
  - **Szukaj w tekście…** (Ctrl+F) podświetla wszystkie trafienia; Enter przechodzi do następnego.
  - Pasek stanu pokazuje liczbę stron i słów, wybrany język oraz **pewność OCR** — średnią pewność silnika (im bliżej 100%, tym mniej błędów; poniżej ok. 80% warto sprawdzić tekst dokładniej).

## Tryby pracy

- **Podstawowy** — czysty tekst. Działa na każdym komputerze.
- **Pełny** — dodatkowo odtwarza strukturę dokumentu (nagłówki, listy, tabele, obrazy) i zapisuje edytowalny DOCX. To **czysty dokument do dalszej pracy, a nie kopia wyglądu strony 1:1** — układ wielokolumnowy i dokładne położenie elementów mogą wymagać ręcznej poprawki. Tryb pełny wymaga dołączonych modeli; jeśli ich nie ma, opcja jest wyszarzona.

## Formaty zapisu

| Format | Zawartość |
|---|---|
| **DOCX** | edytowalny dokument Word; w trybie pełnym z nagłówkami, listami, tabelami i obrazami |
| **TXT** | czysty tekst (UTF-8) w widoku, który jest aktualnie wybrany |
| **PDF (z tekstem)** | oryginalne strony z ukrytą warstwą tekstu — tekst można zaznaczać i wyszukiwać; zapis trwa chwilę, bo strony są rozpoznawane ponownie |
| **Markdown** | tekst z prostym formatowaniem |
| **HTML** | strona do otwarcia w przeglądarce, bez żadnych zasobów z internetu |

Domyślna nazwa pliku to `<nazwa>_ocr.<rozszerzenie>`. Aplikacja **nigdy nie nadpisuje pliku bez pytania**. Opcja **Zachowaj strukturę (tryb pełny)** po wyłączeniu zapisuje czysty tekst w akapitach także w trybie pełnym.

## Jak uzyskać lepszy wynik

- Skanuj w rozdzielczości **300 dpi** (200 dpi zwykle też wystarczy). Niższe rozdzielczości aplikacja powiększa automatycznie, ale jakość spada.
- Zostaw włączoną **automatyczną obróbkę obrazu** — prostuje krzywe skany, usuwa szum i poprawia kontrast.
- Wybierz właściwy **język OCR**. Dla dokumentów polskich z wtrąceniami angielskimi najlepszy jest *Polski + Angielski*.
- Pismo odręczne nie jest obsługiwane.

## Prywatność

- Aplikacja **nie wykonuje żadnych połączeń sieciowych** — znacznik w nagłówku przypomina o tym stale.
- Kolejka i miniatury istnieją tylko w pamięci. Po zamknięciu aplikacji nie zostaje lista ostatnio otwartych plików ani historia. Folder tymczasowy jest czyszczony przy uruchomieniu i zamknięciu.
- Pliki wynikowe trafiają tylko tam, gdzie wskażesz.
- Logi techniczne nie zawierają treści dokumentów ani nazw plików.
- Skopiowany tekst trafia do schowka systemowego. W ustawieniach można włączyć automatyczne czyszczenie schowka po kilku minutach. Pamiętaj, że menedżery schowka mogą zachować własną kopię.

## Skróty klawiszowe

| Skrót | Działanie |
|---|---|
| Ctrl+O | dodaj pliki |
| Ctrl+S | zapisz w domyślnym formacie |
| Ctrl+C | kopiuj zaznaczenie albo cały tekst (gdy fokus jest na tekście) |
| Ctrl+F | szukaj w tekście |
| Enter / Shift+Enter | następne / poprzednie trafienie |
| PgUp / PgDn | poprzednia / następna strona podglądu |
| Ctrl++ / Ctrl+- | powiększ / pomniejsz podgląd |
| Esc | anuluj przetwarzanie lub zapis |
| Delete | usuń zaznaczony plik z kolejki |
| Ctrl+, | ustawienia |
| F1 | ta pomoc |

## Komunikaty o błędach

| Komunikat | Co zrobić |
|---|---|
| Plik jest chroniony hasłem | Usuń zabezpieczenie w programie, w którym go utworzono, i dodaj plik ponownie. |
| Nie udało się otworzyć pliku | Plik może być uszkodzony lub niekompletny — spróbuj zapisać go ponownie. |
| Ten format nie jest obsługiwany | Użyj PDF, PNG, JPG lub TIFF. |
| Plik jest zbyt duży | Zmniejsz rozdzielczość renderowania PDF w ustawieniach (Przetwarzanie). |
| Nie znaleziono tekstu | Sprawdź, czy skan jest czytelny i czy wybrany jest właściwy język. |
| Brak danych językowych / silnika OCR | Instalacja aplikacji jest niekompletna — zainstaluj ją ponownie. |
