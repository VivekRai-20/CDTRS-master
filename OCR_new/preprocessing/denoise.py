"""
preprocessing/denoise.py
-------------------------
Noise reduction for scanned document images.

Three strategies are available (configured via config.yaml):

  gaussian   – fast, good for mild Gaussian noise
  median     – effective for salt-and-pepper noise
  nlm        – Non-Local Means (slower but highest quality)

The active strategy is selected from config["preprocessing"]["denoise_method"]
(default: "median").
"""

from __future__ import annotations

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

# Supported method names
_METHODS = {"gaussian", "median", "nlm"}


def denoise(image: np.ndarray, config: dict | None = None) -> np.ndarray:
    """
    Apply denoising to *image*.

    Parameters
    ----------
    image : np.ndarray
        BGR or grayscale document image.
    config : dict, optional
        Application config.  The relevant key is
        ``config["preprocessing"]["denoise_method"]`` (str).

    Returns
    -------
    np.ndarray
        Denoised image of the same dtype and channel count.
    """
    cfg = (config or {}).get("preprocessing", {})
    method = str(cfg.get("denoise_method", "median")).lower()

    if method not in _METHODS:
        log.warning(
            "Unknown denoise method '%s'. Falling back to 'median'.", method
        )
        method = "median"

    log.debug("Denoising with method='%s'", method)

    if method == "gaussian":
        return _gaussian(image, cfg)
    if method == "median":
        return _median(image, cfg)
    # nlm
    return _nlm(image, cfg)


# ──────────────────────────────────────────────────────────────────────────────
# Strategy implementations
# ──────────────────────────────────────────────────────────────────────────────

def _gaussian(image: np.ndarray, cfg: dict) -> np.ndarray:
    """Gaussian blur denoising."""
    ksize = int(cfg.get("gaussian_kernel", 3))
    ksize = ksize if ksize % 2 == 1 else ksize + 1  # must be odd
    return cv2.GaussianBlur(image, (ksize, ksize), 0)


def _median(image: np.ndarray, cfg: dict) -> np.ndarray:
    """Median blur denoising — effective against salt-and-pepper noise."""
    ksize = int(cfg.get("median_kernel", 3))
    ksize = ksize if ksize % 2 == 1 else ksize + 1
    return cv2.medianBlur(image, ksize)


def _nlm(image: np.ndarray, cfg: dict) -> np.ndarray:
    """
    Non-Local Means denoising — highest quality, but slower.

    Works on both grayscale and colour images.
    """
    h = float(cfg.get("nlm_h", 10))
    template_window = int(cfg.get("nlm_template_window", 7))
    search_window = int(cfg.get("nlm_search_window", 21))

    if image.ndim == 2:
        return cv2.fastNlMeansDenoising(
            image,
            h=h,
            templateWindowSize=template_window,
            searchWindowSize=search_window,
        )
    else:
        return cv2.fastNlMeansDenoisingColored(
            image,
            h=h,
            hColor=h,
            templateWindowSize=template_window,
            searchWindowSize=search_window,
        )
