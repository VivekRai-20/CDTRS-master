"""
preprocessing/threshold.py
---------------------------
Image binarisation / thresholding for scanned documents.

Three modes are supported (configured via config.yaml):

  otsu        – Otsu's global thresholding (best for bimodal histograms)
  adaptive    – Adaptive (local) thresholding (best for uneven lighting)
  simple      – Fixed global threshold

Config key: config["preprocessing"]["threshold_method"]
            ("otsu" | "adaptive" | "simple"), default: "otsu"

Note
----
Aggressive binarisation can destroy fine handwriting strokes.
The preprocessing pipeline in image_preprocessor.py should apply
thresholding selectively (e.g., skip for handwriting-only regions or
reduce the block size for adaptive mode).
"""

from __future__ import annotations

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

_METHODS = {"otsu", "adaptive", "simple"}


def threshold(image: np.ndarray, config: dict | None = None) -> np.ndarray:
    """
    Binarise *image*.

    Parameters
    ----------
    image : np.ndarray
        BGR or grayscale image.
    config : dict, optional
        Full application config.

    Returns
    -------
    np.ndarray
        Binarised (single-channel) image as uint8.
    """
    cfg = (config or {}).get("preprocessing", {})
    method = str(cfg.get("threshold_method", "otsu")).lower()

    if method not in _METHODS:
        log.warning("Unknown threshold method '%s'. Falling back to 'otsu'.", method)
        method = "otsu"

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    log.debug("Thresholding with method='%s'", method)

    if method == "otsu":
        return _otsu(gray)
    if method == "adaptive":
        return _adaptive(gray, cfg)
    # simple
    return _simple(gray, cfg)


# ──────────────────────────────────────────────────────────────────────────────
# Strategy implementations
# ──────────────────────────────────────────────────────────────────────────────

def _otsu(gray: np.ndarray) -> np.ndarray:
    """Otsu's global thresholding."""
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _adaptive(gray: np.ndarray, cfg: dict) -> np.ndarray:
    """
    Adaptive Gaussian thresholding.

    Handles uneven illumination better than Otsu for scanned documents.
    """
    block_size = int(cfg.get("adaptive_block_size", 11))
    c_constant = int(cfg.get("adaptive_c", 2))

    # block_size must be odd and >= 3
    if block_size < 3:
        block_size = 3
    if block_size % 2 == 0:
        block_size += 1

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c_constant,
    )
    return binary


def _simple(gray: np.ndarray, cfg: dict) -> np.ndarray:
    """Simple fixed-value thresholding."""
    thresh_value = int(cfg.get("simple_threshold_value", 127))
    _, binary = cv2.threshold(gray, thresh_value, 255, cv2.THRESH_BINARY)
    return binary
