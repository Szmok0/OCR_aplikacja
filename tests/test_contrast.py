"""WCAG AA contrast of the theme tokens (§7.7, stage 5 acceptance)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from lokalocr.ui.theme import DARK, LIGHT, Tokens


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (foreground, background, minimum): 4.5 for normal text, 3.0 for large/bold
# text and UI components (WCAG 2.1 AA, 1.4.3 and 1.4.11).
PAIRS = [
    ("text", "bg", 4.5),
    ("text", "surface", 4.5),
    ("text", "surface_alt", 4.5),
    ("text_muted", "bg", 4.5),
    ("text_muted", "surface_alt", 4.5),
    ("text", "accent_soft", 4.5),  # selected queue item
    ("on_accent", "accent", 4.5),  # primary buttons
    ("accent", "surface_alt", 4.5),  # link "Wyczyść", active tab
    ("success", "surface_alt", 4.5),  # "Gotowe"
    ("danger", "surface_alt", 4.5),  # errors, "Anuluj"
    ("danger", "danger_soft", 4.5),  # error banner, cancel hover
    ("success", "accent_soft", 4.5),  # status of the selected queue item
    ("danger", "accent_soft", 4.5),
    ("text_muted", "accent_soft", 4.5),
    ("accent", "bg", 3.0),  # focus rings, toggles
]


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=["light", "dark"])
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_contrast_aa(tokens: Tokens, fg: str, bg: str, minimum: float) -> None:
    ratio = contrast(getattr(tokens, fg), getattr(tokens, bg))
    assert ratio >= minimum, f"{fg} on {bg}: {ratio:.2f} < {minimum}"
