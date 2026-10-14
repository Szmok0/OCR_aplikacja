# Lista kontrolna „offline” przed wydaniem (§6)

Ręczny test na komputerze docelowym (Windows). Zajmuje ok. 15 minut. Do testu używaj **wyłącznie dokumentów fikcyjnych** (np. wygenerowanych przez `scripts/make_fixtures.py`).

## 1. Komputer bez sieci

- [ ] Odłącz sieć (Wi-Fi wyłączone, kabel odłączony) i uruchom `LokalOCR.exe`.
- [ ] Okno otwiera się bez komunikatów o błędach i bez okien powitalnych; w nagłówku widać „Offline — brak połączeń sieciowych”.
- [ ] Przetwórz plik PNG, wielostronicowy PDF i TIFF — wynik się pojawia.
- [ ] Zapisz wynik do DOCX, TXT, PDF (z tekstem), Markdown i HTML; otwórz pliki w Word/LibreOffice i przeglądarce. Tekst w PDF da się zaznaczyć i wyszukać (Ctrl+F w czytniku PDF).
- [ ] `LokalOCR.exe --selftest raport.json` → w pliku `"ok": true`.

## 2. Zapora blokująca ruch wychodzący

- [ ] Włącz sieć, ale w *Zaporze Windows Defender → Reguły wychodzące* dodaj regułę **blokującą** dla `LokalOCR.exe`, `lokalocr-cli.exe` i `_internal\tesseract\tesseract.exe` (albo zablokuj cały ruch wychodzący w profilu).
- [ ] Powtórz test z punktu 1 — wszystko działa tak samo.

## 3. Obserwacja ruchu

- [ ] Przy włączonej sieci (bez blokady) uruchom **Monitor zasobów** (`resmon`) → karta *Sieć* → *Aktywność sieciowa* albo `TCPView` (Sysinternals).
- [ ] Przetwórz kilka dokumentów, zapisz wyniki, otwórz ustawienia i pomoc.
- [ ] Procesy `LokalOCR.exe`, `lokalocr-cli.exe` i `tesseract.exe` **nie pojawiają się** na liście połączeń sieciowych (dopuszczalne są tylko połączenia z `127.0.0.1`, używane wewnętrznie).

## 4. Brak śladów po zamknięciu

- [ ] Zamknij aplikację.
- [ ] Folder tymczasowy (`%TEMP%\LokalOCR-<użytkownik>` albo wskazany w ustawieniach) nie istnieje lub jest pusty.
- [ ] W `%APPDATA%\LokalOCR\settings.json` nie ma nazw ani ścieżek przetwarzanych dokumentów.
- [ ] W logach (`%LOCALAPPDATA%\LokalOCR\logs\lokalocr.log`) nie ma treści dokumentów ani nazw plików (wyszukaj np. nazwę testowego pliku i fragment rozpoznanego tekstu).
- [ ] Po ponownym uruchomieniu kolejka jest pusta — brak listy „ostatnio otwarte”.
- [ ] Otwórz i zapisz plik przyciskiem **Wybierz pliki…** / **Zapisz**, potem sprawdź, że nazwa dokumentu **nie** pojawiła się w *Eksploratorze → Szybki dostęp → Ostatnie pliki* (folder `shell:recent`) ani na liście skoku (jump list) ikony LokalOCR na pasku zadań.
- [ ] W rejestrze (`regedit`) klucz `HKEY_CURRENT_USER\Software\QtProject\OrganizationDefaults\FileDialog` nie zawiera wartości `history` ani `lastVisited` wskazujących foldery z dokumentami.

## 5. Ustawienia Windows (poza aplikacją, zalecane)

Aplikacja nie wysyła niczego, ale sam system może. Przy dokumentach wrażliwych warto sprawdzić:

- [ ] *Zabezpieczenia Windows → Ochrona przed wirusami → Automatyczne przesyłanie próbek*: **wyłączone** (Defender może wysyłać do Microsoftu podejrzane pliki, także dokumenty).
- [ ] Folder z dokumentami nie jest synchronizowany z chmurą (kopia zapasowa folderów w OneDrive często obejmuje *Dokumenty* i *Pulpit*).
- [ ] Przy pierwszym uruchomieniu SmartScreen sprawdza reputację samego programu `LokalOCR.exe` (skrót pliku programu, nie dokumentów) — to normalne.

## Wynik

Data: ________  Wersja: ________  Wynik: OK / uwagi: ______________________
