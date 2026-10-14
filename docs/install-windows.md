# LokalOCR — instalacja na Windows (prototyp)

## Pobranie

Najnowsza wersja jest zawsze pod tym samym adresem (strona **Releases** repozytorium, link także w prawej kolumnie strony głównej repozytorium na GitHubie):

- strona wydania: https://github.com/Szmok0/OCR_aplikacja/releases/latest
- bezpośrednio, tryb podstawowy: https://github.com/Szmok0/OCR_aplikacja/releases/latest/download/LokalOCR-windows-basic.zip
- bezpośrednio, tryb pełny: https://github.com/Szmok0/OCR_aplikacja/releases/latest/download/LokalOCR-windows-full.zip

Wersja publikuje się sama po każdej zmianie scalonej do `main` (ok. 15 minut po scaleniu).

## Instalacja

1. Rozpakuj (prawy przycisk → **Wyodrębnij wszystko…**) archiwum `LokalOCR-windows-basic.zip` (albo `-full`) do dowolnego folderu, np. `C:\Programy`. Nie uruchamiaj programu z wnętrza ZIP-a. Uprawnienia administratora nie są potrzebne.
2. Uruchom **`LokalOCR.exe`** z rozpakowanego folderu `LokalOCR`.
3. Przy pierwszym uruchomieniu Windows może pokazać okno **„System Windows ochronił ten komputer”** (SmartScreen) — program nie jest podpisany cyfrowo. Kliknij **Więcej informacji → Uruchom mimo to**. Niektóre programy antywirusowe oznaczają aplikacje zbudowane PyInstallerem jako podejrzane (fałszywy alarm).

Tesseract (silnik OCR) i dane językowe polski + angielski są w pakiecie — nic więcej nie trzeba instalować.

## Warianty

- **basic** — tryb podstawowy (czysty tekst, TXT, DOCX, PDF z tekstem, Markdown, HTML). Mały i szybki, działa na każdym laptopie.
- **full** — dodatkowo tryb pełny (struktura dokumentu, tabele, obrazy) z lokalnymi modelami. Duży pakiet; tryb pełny działa na procesorze, więc jest wolniejszy (kilka–kilkanaście sekund na stronę).

## Sprawdzenie instalacji

W wierszu poleceń (w folderze programu):

```
LokalOCR.exe --selftest raport.json
```

Program rozpozna wzorcowy polski tekst i zapisze wynik do `raport.json` (`"ok": true` = wszystko działa).

Wiersz poleceń: `lokalocr-cli.exe --help`.

## Prywatność

Aplikacja nie łączy się z internetem. Ustawienia są w `%APPDATA%\LokalOCR`, logi (bez treści dokumentów i nazw plików) w `%LOCALAPPDATA%\LokalOCR\logs`. Aby całkowicie usunąć program, usuń jego folder i te dwa foldery.
