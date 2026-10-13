from __future__ import annotations

import numpy as np
import pytest

import make_fixtures as fx
from lokalocr import preprocess as pp


@pytest.fixture(scope="module")
def page() -> fx.SynthPage:
    return fx.make_contract(150, pages=1).pages[0]


@pytest.mark.parametrize("angle", [-4.0, -1.5, 2.0, 5.0])
def test_estimate_skew(page: fx.SynthPage, angle: float) -> None:
    gray = np.asarray(fx.rotate(page.image, angle).convert("L"))
    assert pp.estimate_skew(gray) == pytest.approx(angle, abs=0.3)


def test_straight_page_has_no_skew(page: fx.SynthPage) -> None:
    assert abs(pp.estimate_skew(np.asarray(page.image.convert("L")))) < 0.2


def test_blank_page_skew_is_zero() -> None:
    assert pp.estimate_skew(np.full((200, 200), 255, dtype=np.uint8)) == 0.0


def test_noise_estimate_separates_clean_and_noisy(page: fx.SynthPage) -> None:
    clean = pp.estimate_noise(np.asarray(page.image.convert("L")))
    noisy = pp.estimate_noise(np.asarray(fx.add_noise(page.image).convert("L")))
    assert clean < pp.NOISE_SIGMA_THRESHOLD < noisy


def test_low_resolution_is_upscaled(page: fx.SynthPage) -> None:
    out, dpi = pp.preprocess(page.image, 150)
    assert dpi == 300
    assert out.width >= page.image.width * 2 - 2


def test_disabled_returns_greyscale_same_size(page: fx.SynthPage) -> None:
    out, dpi = pp.preprocess(page.image, 150, pp.PreprocessOptions(enabled=False))
    assert (out.mode, out.size, dpi) == ("L", page.image.size, 150)


def test_contrast_stretch_uses_full_range(page: fx.SynthPage) -> None:
    faint = fx.low_contrast(page.image)
    out, _ = pp.preprocess(faint, 300, pp.PreprocessOptions(deskew=False, denoise=False))
    arr = np.asarray(out)
    assert arr.min() < 30 and arr.max() > 225


def test_deskew_straightens_page(page: fx.SynthPage) -> None:
    rotated = fx.rotate(page.image, 3.0)
    out, _ = pp.preprocess(rotated, 300, pp.PreprocessOptions(denoise=False, contrast=False))
    assert abs(pp.estimate_skew(np.asarray(out))) < 0.3
