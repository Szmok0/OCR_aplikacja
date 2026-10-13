"""Page image preprocessing before OCR (§3, §7.5 "Przetwarzanie").

All steps work on greyscale and are optional. The defaults were chosen by
measuring CER on the synthetic set (see ``docs/quality/cer-baseline.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image

__all__ = [
    "PreprocessOptions",
    "estimate_noise",
    "estimate_skew",
    "preprocess",
    "rotate_page",
]

Gray = npt.NDArray[np.uint8]


def _u8(array: Any) -> Gray:
    """OpenCV stubs return loosely typed arrays; results here are always uint8."""
    return np.asarray(array, dtype=np.uint8)


# Tesseract is most accurate around 300 dpi; low-resolution input is upscaled.
TARGET_DPI = 300
MIN_DPI_FOR_UPSCALE = 250
MAX_UPSCALE = 2.5


@dataclass(frozen=True, slots=True)
class PreprocessOptions:
    enabled: bool = True
    deskew: bool = True
    denoise: bool = True
    contrast: bool = True
    upscale: bool = True


def _to_gray(image: Image.Image) -> Gray:
    return np.asarray(image.convert("L"), dtype=np.uint8)


def estimate_skew(gray: Gray, max_angle: float = 10.0) -> float:
    """Estimate text skew in degrees (positive = counter-clockwise) via projection profiles.

    Text lines produce sharp peaks in the horizontal projection when the page
    is straight; the angle maximising the profile variance wins.
    """
    h, w = gray.shape
    scale = min(1.0, 1000.0 / max(h, w))
    small = (
        cv2.resize(
            gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
        )
        if scale < 1.0
        else gray
    )
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if cv2.countNonZero(ink) < 50:
        return 0.0
    sh, sw = ink.shape
    center = (sw / 2, sh / 2)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(ink, m, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        profile = rotated.sum(axis=1, dtype=np.float64)
        return float(np.var(profile))

    coarse = np.arange(-max_angle, max_angle + 1e-9, 0.5)
    best = max(coarse, key=score)
    fine = np.arange(best - 0.5, best + 0.5 + 1e-9, 0.1)
    best = max(fine, key=score)
    # The image needs rotating by ``best`` to be straight, i.e. it is skewed by -best.
    return -float(round(best, 2))


def rotate_page(gray: Gray, angle: float) -> Gray:
    """Rotate by ``angle`` degrees counter-clockwise, keeping the full page and a white border."""
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return _u8(
        cv2.warpAffine(
            gray,
            m,
            (nw, nh),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )
    )


_NOISE_KERNEL = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
# Above this estimated sigma the (slow) non-local-means pass is worth it.
NOISE_SIGMA_THRESHOLD = 6.0


def estimate_noise(gray: Gray) -> float:
    """Fast noise sigma estimate (Immerkaer 1996) on a central crop."""
    h, w = gray.shape
    ch, cw = min(h, 1200), min(w, 1200)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    crop = gray[y0 : y0 + ch, x0 : x0 + cw].astype(np.float32)
    if ch < 3 or cw < 3:
        return 0.0
    response = cv2.filter2D(crop, -1, _NOISE_KERNEL)[1:-1, 1:-1]
    return float(np.sqrt(np.pi / 2) * np.abs(response).sum() / (6 * (cw - 2) * (ch - 2)))


def _denoise(gray: Gray) -> Gray:
    # Median removes salt-and-pepper specks cheaply; non-local means handles
    # strong Gaussian scanner noise but costs seconds per page, so it only
    # runs when the page is measurably noisy.
    out = _u8(cv2.medianBlur(gray, 3))
    if estimate_noise(gray) > NOISE_SIGMA_THRESHOLD:
        out = _u8(
            cv2.fastNlMeansDenoising(out, None, h=12, templateWindowSize=7, searchWindowSize=21)
        )
    return out


def _stretch_contrast(gray: Gray) -> Gray:
    # Stretch between robust percentiles so faint scans use the full range.
    cdf = np.cumsum(np.bincount(gray.ravel(), minlength=256))
    total = cdf[-1]
    lo = int(np.searchsorted(cdf, total * 0.01))
    hi = int(np.searchsorted(cdf, total * 0.99))
    if hi - lo < 1:
        return gray
    lut = np.clip((np.arange(256, dtype=np.float32) - lo) * (255.0 / (hi - lo)), 0, 255)
    return _u8(cv2.LUT(gray, lut.astype(np.uint8)))


def preprocess(
    image: Image.Image, dpi: int, options: PreprocessOptions | None = None
) -> tuple[Image.Image, int]:
    """Return the cleaned greyscale image and its effective dpi."""
    opts = options or PreprocessOptions()
    gray = _to_gray(image)
    if not opts.enabled:
        return Image.fromarray(gray), dpi

    effective_dpi = dpi
    if opts.upscale and dpi < MIN_DPI_FOR_UPSCALE:
        factor = min(MAX_UPSCALE, TARGET_DPI / dpi)
        gray = _u8(cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC))
        effective_dpi = round(dpi * factor)
    if opts.contrast:
        gray = _stretch_contrast(gray)
    if opts.denoise:
        gray = _denoise(gray)
    if opts.deskew:
        angle = estimate_skew(gray)
        if abs(angle) >= 0.2:
            gray = rotate_page(gray, -angle)
    return Image.fromarray(gray), effective_dpi
