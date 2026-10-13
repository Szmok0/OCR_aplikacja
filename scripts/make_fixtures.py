"""Generate synthetic test documents with known ground truth (CLAUDE.md §9).

All content is fictional. Documents mirror the acceptance scenarios (§1):
a CV (headings, bullet list, photo placeholder), an invoice (table) and a
multi-page contract scan. Each can be rendered at several resolutions and
degraded (rotation, noise, low contrast).

Usage::

    python scripts/make_fixtures.py [--out tests/fixtures/generated]

Tests import this module directly (``pythonpath`` in pyproject.toml).
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "fonts"
SANS = FONTS_DIR / "DejaVuSans.ttf"
SANS_BOLD = FONTS_DIR / "DejaVuSans-Bold.ttf"
SERIF = FONTS_DIR / "DejaVuSerif.ttf"

A4_INCHES = (8.27, 11.69)

PANGRAM = "Zażółć gęślą jaźń. ZAŻÓŁĆ GĘŚLĄ JAŹŃ."


@dataclass
class SynthPage:
    image: Image.Image
    truth: list[str]  # ground-truth lines in reading order
    dpi: int


@dataclass
class SynthDocument:
    name: str
    pages: list[SynthPage] = field(default_factory=list)

    @property
    def truth(self) -> str:
        return "\n".join("\n".join(p.truth) for p in self.pages)


class _Canvas:
    """A4 page with a cursor; ``pt`` sizes are converted with the page dpi."""

    def __init__(self, dpi: int) -> None:
        self.dpi = dpi
        w, h = (round(v * dpi) for v in A4_INCHES)
        self.image = Image.new("RGB", (w, h), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.margin = self.px(64)
        self.x = self.margin
        self.y = self.margin
        self.right = w - self.margin
        self.truth: list[str] = []

    def px(self, pt: float) -> int:
        return round(pt * self.dpi / 72)

    def font(self, path: Path, size_pt: float) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(path), self.px(size_pt))

    def text(
        self,
        line: str,
        *,
        font: Path = SANS,
        size: float = 11,
        indent: float = 0,
        gap: float = 1.45,
        x: int | None = None,
        record: bool = True,
    ) -> None:
        f = self.font(font, size)
        self.draw.text(
            ((x if x is not None else self.x) + self.px(indent), self.y), line, "black", f
        )
        self.y += round(self.px(size) * gap)
        if record:
            self.truth.append(line)

    def paragraph(
        self,
        text: str,
        *,
        font: Path = SANS,
        size: float = 11,
        indent: float = 0,
        width: int | None = None,
        x: int | None = None,
    ) -> None:
        f = self.font(font, size)
        left = (x if x is not None else self.x) + self.px(indent)
        max_w = width if width is not None else self.right - left
        line = ""
        for word in text.split():
            candidate = f"{line} {word}".strip()
            if line and f.getlength(candidate) > max_w:
                self.text(line, font=font, size=size, x=left)
                line = word
            else:
                line = candidate
        if line:
            self.text(line, font=font, size=size, x=left)

    def space(self, pt: float) -> None:
        self.y += self.px(pt)

    def page(self) -> SynthPage:
        return SynthPage(self.image, self.truth, self.dpi)


# --- documents ----------------------------------------------------------------


def make_cv(dpi: int = 300) -> SynthDocument:
    c = _Canvas(dpi)
    # Photo placeholder: grey box with a simple silhouette (no real face).
    ph = c.px(110)
    box = (c.margin, c.margin, c.margin + ph, c.margin + round(ph * 1.2))
    c.draw.rectangle(box, fill=(205, 210, 218))
    cx = (box[0] + box[2]) // 2
    c.draw.ellipse(
        (cx - ph // 5, box[1] + ph // 6, cx + ph // 5, box[1] + ph // 6 + 2 * ph // 5),
        fill=(150, 156, 166),
    )
    c.draw.ellipse(
        (cx - ph // 2.6, box[1] + ph * 0.7, cx + ph // 2.6, box[3] + ph // 2), fill=(150, 156, 166)
    )
    c.draw.rectangle((box[0], box[3], box[2], box[3] + ph), fill="white")

    left = box[2] + c.px(24)
    c.y = c.margin + c.px(8)
    c.text("Zofia Przykładowa", font=SANS_BOLD, size=22, x=left)
    c.text("Specjalistka ds. księgowości", size=13, x=left)
    c.space(6)
    for line in ("Tel. +48 500 000 000", "zofia.przykladowa@example.com", "Gdańsk, Polska"):
        c.text(line, size=10.5, x=left)
    c.y = max(c.y, box[3]) + c.px(18)

    def heading(t: str) -> None:
        c.space(8)
        c.text(t, font=SANS_BOLD, size=13)
        c.draw.line(
            (c.margin, c.y - c.px(4), c.right, c.y - c.px(4)),
            fill=(60, 60, 60),
            width=max(1, c.px(0.8)),
        )
        c.space(4)

    heading("PODSUMOWANIE")
    c.paragraph(
        "Księgowa z ośmioletnim doświadczeniem w obsłudze małych i średnich firm. "
        "Zajmuję się rozliczeniami podatkowymi, płacami oraz sprawozdawczością. "
        "Cenię rzetelność, dokładność i spokojną współpracę z zespołem."
    )
    heading("DOŚWIADCZENIE ZAWODOWE")
    c.text("Główna księgowa | Biuro Rachunkowe Żuraw Sp. z o.o.", font=SANS_BOLD, size=11)
    c.text("03.2019 - obecnie", size=10)
    for item in (
        "Prowadzenie pełnej księgowości dla czterdziestu klientów",
        "Przygotowanie deklaracji VAT, CIT i PIT",
        "Nadzór nad zespołem pięciu osób",
        "Wdrożenie elektronicznego obiegu dokumentów",
    ):
        c.text(f"• {item}", indent=10)
    c.space(4)
    c.text("Samodzielna księgowa | Hurtownia Źródło S.A.", font=SANS_BOLD, size=11)
    c.text("06.2016 - 02.2019", size=10)
    for item in ("Rozliczanie należności i zobowiązań", "Uzgadnianie sald z kontrahentami"):
        c.text(f"• {item}", indent=10)
    heading("WYKSZTAŁCENIE")
    c.text("Uniwersytet Gdański, Wydział Zarządzania", size=11)
    c.text("Finanse i rachunkowość, studia magisterskie, 2011 - 2016", size=10.5)
    heading("JĘZYKI")
    c.text("Polski - ojczysty; Angielski - B2; Niemiecki - A2", size=11)
    return SynthDocument("cv", [c.page()])


INVOICE_ITEMS = [
    ("1", "Usługa księgowa - październik", "1", "1 200,00", "1 200,00"),
    ("2", "Żółte segregatory A4 (opakowanie)", "4", "35,50", "142,00"),
    ("3", "Szkolenie z obsługi programu", "2", "450,00", "900,00"),
    ("4", "Licencja roczna - moduł płace", "1", "780,00", "780,00"),
]


def make_invoice(dpi: int = 300) -> SynthDocument:
    c = _Canvas(dpi)
    c.text("FAKTURA VAT nr FV/2024/10/042", font=SANS_BOLD, size=18)
    c.text("Data wystawienia: 15.10.2024    Termin płatności: 29.10.2024", size=10.5)
    c.space(10)
    col2 = c.margin + (c.right - c.margin) // 2
    top = c.y
    c.text("Sprzedawca:", font=SANS_BOLD, size=11)
    c.text("Przykładowa Firma Sp. z o.o.", size=10.5)
    c.text("ul. Łąkowa 12, 80-001 Gdańsk", size=10.5)
    c.text("NIP 000-000-00-00", size=10.5)
    bottom = c.y
    c.y = top
    c.text("Nabywca:", font=SANS_BOLD, size=11, x=col2)
    c.text("Ćma i Wspólnicy S.C.", size=10.5, x=col2)
    c.text("ul. Źródlana 5, 60-002 Poznań", size=10.5, x=col2)
    c.text("NIP 111-111-11-11", size=10.5, x=col2)
    c.y = max(bottom, c.y) + c.px(16)

    headers = ("Lp.", "Nazwa towaru lub usługi", "Ilość", "Cena netto", "Wartość netto")
    widths = (0.07, 0.48, 0.1, 0.17, 0.18)
    table_w = c.right - c.margin
    xs = [c.margin]
    for w in widths:
        xs.append(xs[-1] + round(w * table_w))
    row_h = c.px(22)
    pad = c.px(5)
    line_w = max(1, c.px(0.8))
    rows = [headers, *INVOICE_ITEMS]
    for r, row in enumerate(rows):
        y0 = c.y
        font = c.font(SANS_BOLD if r == 0 else SANS, 10)
        for i, cell in enumerate(row):
            c.draw.text((xs[i] + pad, y0 + pad), cell, "black", font)
        c.draw.rectangle((xs[0], y0, xs[-1], y0 + row_h), outline="black", width=line_w)
        for x in xs[1:-1]:
            c.draw.line((x, y0, x, y0 + row_h), fill="black", width=line_w)
        c.truth.append(" ".join(row))
        c.y += row_h
    c.space(14)
    c.text("Razem netto: 3 022,00 zł", font=SANS_BOLD, size=11)
    c.text("VAT 23%: 695,06 zł", size=11)
    c.text("Do zapłaty: 3 717,06 zł", font=SANS_BOLD, size=12)
    c.text("Słownie: trzy tysiące siedemset siedemnaście złotych 06/100", size=10)
    return SynthDocument("invoice", [c.page()])


_CONTRACT_SENTENCES = [
    "Zamawiający zleca, a Wykonawca zobowiązuje się wykonać dzieło opisane w niniejszej umowie.",
    "Wykonawca oświadcza, że posiada wiedzę i doświadczenie niezbędne do należytego wykonania dzieła.",
    "Strony ustalają, że dzieło zostanie wydane Zamawiającemu w terminie czternastu dni roboczych.",
    "Za wykonanie dzieła Zamawiający zapłaci Wykonawcy wynagrodzenie w wysokości określonej poniżej.",
    "Wynagrodzenie płatne będzie przelewem na rachunek bankowy wskazany przez Wykonawcę.",
    "W przypadku zwłoki w wydaniu dzieła Wykonawca zapłaci karę umowną za każdy dzień opóźnienia.",
    "Zmiany niniejszej umowy wymagają formy pisemnej pod rygorem nieważności.",
    "W sprawach nieuregulowanych zastosowanie mają przepisy Kodeksu cywilnego.",
    "Spory wynikłe z umowy rozstrzygać będzie sąd właściwy dla siedziby Zamawiającego.",
    "Umowę sporządzono w dwóch jednobrzmiących egzemplarzach, po jednym dla każdej ze stron.",
    "Źródłem wątpliwości nie może być żadne postanowienie, którego treść jest jednoznaczna.",
    "Każda ze stron może żądać udostępnienia dokumentów związanych z wykonaniem umowy.",
]


def make_contract(dpi: int = 300, pages: int = 3) -> SynthDocument:
    rng = random.Random(7)
    doc = SynthDocument("contract")
    paragraph_no = 1
    for page_no in range(1, pages + 1):
        c = _Canvas(dpi)
        if page_no == 1:
            c.text("UMOWA O DZIEŁO nr 7/2024", font=SANS_BOLD, size=16)
            c.text("zawarta w dniu 2 września 2024 r. w Łodzi", font=SERIF, size=11)
            c.space(6)
            c.paragraph(PANGRAM, font=SERIF, size=11)
            c.space(6)
        while c.y < c.image.height - c.px(170):
            c.text(f"§ {paragraph_no}", font=SANS_BOLD, size=12)
            text = " ".join(rng.sample(_CONTRACT_SENTENCES, 3))
            c.paragraph(text, font=SERIF, size=11)
            c.space(8)
            paragraph_no += 1
        c.y = c.image.height - c.px(60)
        c.text(f"Strona {page_no} z {pages}", font=SERIF, size=9)
        doc.pages.append(c.page())
    return doc


DOCUMENTS: dict[str, Callable[[int], SynthDocument]] = {
    "cv": make_cv,
    "invoice": make_invoice,
    "contract": make_contract,
}


# --- degradations ---------------------------------------------------------------


def rotate(image: Image.Image, degrees: float) -> Image.Image:
    return image.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white")


def add_noise(
    image: Image.Image, sigma: float = 28.0, salt: float = 0.004, seed: int = 1
) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = np.asarray(image.convert("L"), dtype=np.float32)
    arr = arr + rng.normal(0.0, sigma, arr.shape).astype(np.float32)
    mask = rng.random(arr.shape)
    arr[mask < salt / 2] = 0
    arr[mask > 1 - salt / 2] = 255
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGB")


def low_contrast(image: Image.Image, low: int = 105, high: int = 190) -> Image.Image:
    arr = np.asarray(image.convert("L"), dtype=np.float32)
    arr = low + arr * (high - low) / 255.0
    return Image.fromarray(arr.astype(np.uint8)).convert("RGB")


VARIANTS: dict[str, Callable[[Image.Image], Image.Image]] = {
    "clean": lambda im: im,
    "rotated": lambda im: rotate(im, 3.0),
    "noisy": add_noise,
    "lowcontrast": low_contrast,
}


def degrade(doc: SynthDocument, variant: str) -> SynthDocument:
    fn = VARIANTS[variant]
    return SynthDocument(
        f"{doc.name}_{variant}",
        [SynthPage(fn(p.image), p.truth, p.dpi) for p in doc.pages],
    )


# --- writers --------------------------------------------------------------------


def save(doc: SynthDocument, path: Path) -> Path:
    """Save as PNG/JPG (first page), multi-page TIFF or image-only PDF ("scan")."""
    # Copies: Pillow leaves encoder state on an image after a PDF save, which
    # breaks a later TIFF save of the same image object.
    images = [p.image.copy() for p in doc.pages]
    dpi = doc.pages[0].dpi
    suffix = path.suffix.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".pdf":
        images[0].save(path, "PDF", resolution=float(dpi), save_all=True, append_images=images[1:])
    elif suffix in (".tif", ".tiff"):
        images[0].save(
            path,
            "TIFF",
            dpi=(dpi, dpi),
            compression="tiff_deflate",
            save_all=True,
            append_images=images[1:],
        )
    elif suffix in (".jpg", ".jpeg"):
        images[0].save(path, "JPEG", dpi=(dpi, dpi), quality=85)
    elif suffix == ".png":
        images[0].save(path, "PNG", dpi=(dpi, dpi))
    else:
        raise ValueError(f"unsupported fixture format: {suffix}")
    return path


def write_all(out: Path) -> list[Path]:
    written = []
    for name, factory in DOCUMENTS.items():
        for dpi in (150, 200, 300):
            base = factory(dpi)
            for variant in VARIANTS:
                doc = degrade(base, variant)
                stem = f"{doc.name}_{dpi}dpi"
                ext = ".pdf" if name == "contract" else ".png"
                written.append(save(doc, out / f"{stem}{ext}"))
                (out / f"{stem}.txt").write_text(doc.truth + "\n", encoding="utf-8")
        written.append(save(factory(300), out / f"{name}_300dpi.jpg"))
        written.append(save(factory(300), out / f"{name}_300dpi.tif"))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/generated"))
    args = parser.parse_args(argv)
    files = write_all(args.out)
    print(f"Wrote {len(files)} fixture files to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
