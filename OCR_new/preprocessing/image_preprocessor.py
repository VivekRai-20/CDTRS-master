"""
preprocessing/image_preprocessor.py
-------------------------------------
Configurable image preprocessing pipeline for OCR.

Each step can be individually enabled/disabled via config.yaml.
The original input image is NEVER modified — a copy is always returned.

Steps available
---------------
1. grayscale          – Convert to single-channel greyscale
2. denoise            – Non-local means / Gaussian blur
3. contrast_enhance   – CLAHE contrast limited adaptive histogram equalisation
4. threshold          – Adaptive or Otsu binarisation
5. deskew             – Correct small rotations caused by scanning
6. auto_rotate        – Correct 90°/180°/270° page orientation
7. border_removal     – Crop a thin border of scan artefacts
8. upscale            – Upscale low-resolution images
"""

from __future__ import annotations

import math
from typing import Tuple

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


# =========================================================================== #
# Public entry point                                                           #
# =========================================================================== #

def preprocess(image: np.ndarray, config: dict) -> np.ndarray:
    """
    Apply the configured preprocessing pipeline to *image*.

    Parameters
    ----------
    image : np.ndarray
        Input image in BGR (as returned by cv2.imread).
    config : dict
        Full application config dict.

    Returns
    -------
    np.ndarray
        Preprocessed image (BGR).  The input is not modified.
    """
    pre_cfg = config.get("preprocessing", {})

    if not pre_cfg.get("enabled", True):
        log.debug("Preprocessing disabled — passing image through unchanged.")
        return image.copy()

    img = image.copy()

    # ------------------------------------------------------------------ #
    # 1. Optional upscaling first (improves quality of subsequent steps)  #
    # ------------------------------------------------------------------ #
    factor = float(pre_cfg.get("upscale_factor", 1.0))
    if factor > 1.0:
        img = _upscale(img, factor)

    # ------------------------------------------------------------------ #
    # 2. Auto-rotate (coarse: 0/90/180/270)                               #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("auto_rotate", True):
        img = _auto_rotate(img)

    # ------------------------------------------------------------------ #
    # 3. Deskew (fine rotation correction)                                #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("deskew", True):
        img = _deskew(img)

    # ------------------------------------------------------------------ #
    # 4. Grayscale conversion                                             #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("grayscale", True):
        img = _to_grayscale(img)

    # ------------------------------------------------------------------ #
    # 5. Border removal                                                   #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("border_removal", False):
        img = _remove_border(img)

    # ------------------------------------------------------------------ #
    # 6. Denoising                                                        #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("denoise", True):
        img = _denoise(img)

    # ------------------------------------------------------------------ #
    # 7. Contrast enhancement (CLAHE)                                     #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("contrast_enhance", True):
        img = _contrast_enhance(img)

    # ------------------------------------------------------------------ #
    # 8. Thresholding / binarisation                                      #
    # ------------------------------------------------------------------ #
    if pre_cfg.get("threshold", True):
        method = pre_cfg.get("threshold_method", "adaptive")
        img = _threshold(img, method=method)

    # PaddleOCR expects a 3-channel BGR image
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    return img


# =========================================================================== #
# Individual preprocessing steps                                               #
# =========================================================================== #

def _upscale(img: np.ndarray, factor: float) -> np.ndarray:
    h, w = img.shape[:2]
    new_w, new_h = int(w * factor), int(h * factor)
    log.debug("Upscaling %dx%d → %dx%d (×%.1f)", w, h, new_w, new_h, factor)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


def _to_grayscale(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 2:
        return img                              # already greyscale
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _auto_rotate(img: np.ndarray) -> np.ndarray:
    """
    Detect and correct coarse page orientation (0 / 90 / 180 / 270°).
    Uses text-projection heuristic on a binarised image.
    Requires significant confidence ratio (> 1.35x baseline) before rotating.
    """
    try:
        gray = _to_grayscale(img)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        def _score(angle: int) -> float:
            """Row-projection variance — highest for correctly oriented text."""
            rotated = _rotate_exact(bw, angle)
            projection = np.sum(rotated, axis=1).astype(float)
            return float(np.var(projection))

        s0 = _score(0)
        candidates = {0: s0, 90: _score(90), 180: _score(180), 270: _score(270)}
        best_angle = max(candidates, key=lambda a: candidates[a])

        # Require a clear signal (at least 35% higher variance than 0 deg) to rotate
        if best_angle != 0 and s0 > 0 and candidates[best_angle] >= s0 * 1.35:
            log.debug("Auto-rotate: correcting by %d° (score %.1f vs baseline %.1f)", best_angle, candidates[best_angle], s0)
            img = _rotate_exact(img, best_angle)
    except Exception as exc:
        log.debug("Auto-rotate skipped: %s", exc)
    return img


def _rotate_exact(img: np.ndarray, angle: int) -> np.ndarray:
    """Rotate by a multiple of 90° without cropping."""
    if angle == 0:
        return img
    k = (angle // 90) % 4
    return np.rot90(img, k=k)


def _deskew(img: np.ndarray) -> np.ndarray:
    """
    Correct small skew angles (typically < ±15°) caused by scanning.
    Uses Hough-line projection method with consistency checks to avoid
    treating handwriting letter slants as document skew.
    """
    try:
        gray = _to_grayscale(img)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, math.pi / 180, threshold=120)

        if lines is None or len(lines) < 15:
            return img

        angles: list[float] = []
        for line in lines[:80]:
            theta = float(line[0][1])
            angle_deg = math.degrees(theta) - 90.0
            if abs(angle_deg) < 12:
                angles.append(angle_deg)

        if len(angles) < 10:
            return img

        std_dev = float(np.std(angles))
        median_angle = float(np.median(angles))

        # If angles are scattered (typical of handwriting strokes), don't deskew
        if std_dev > 4.0 or abs(median_angle) < 0.5:
            return img

        log.debug("Deskewing: rotating %.2f° (std=%.2f)", -median_angle, std_dev)
        h, w = img.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        M = cv2.getRotationMatrix2D((cx, cy), -median_angle, 1.0)
        img = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception as exc:
        log.debug("Deskew skipped: %s", exc)
    return img


def _remove_border(img: np.ndarray, border_px: int = 10) -> np.ndarray:
    """Crop a thin border of scan artefacts."""
    h, w = img.shape[:2]
    b = min(border_px, h // 10, w // 10)
    return img[b:h - b, b:w - b]


def _denoise(img: np.ndarray) -> np.ndarray:
    """
    Reduce noise while preserving text edges.
    Uses NL-means for greyscale, fastNlMeansDenoisingColored for colour.
    """
    if len(img.shape) == 2:
        return cv2.fastNlMeansDenoising(img, h=10, templateWindowSize=7, searchWindowSize=21)
    return cv2.fastNlMeansDenoisingColored(img, h=10, hColor=10,
                                           templateWindowSize=7, searchWindowSize=21)


def _contrast_enhance(img: np.ndarray) -> np.ndarray:
    """Apply CLAHE contrast enhancement."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    if len(img.shape) == 2:
        return clahe.apply(img)
    # For colour images apply CLAHE on the L channel in LAB colour space
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    l_ch = clahe.apply(l_ch)
    lab = cv2.merge([l_ch, a_ch, b_ch])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _threshold(img: np.ndarray, method: str = "adaptive") -> np.ndarray:
    """
    Binarise the image.

    Parameters
    ----------
    method : str
        "adaptive" – Adaptive Gaussian thresholding (best for uneven lighting).
        "otsu"     – Otsu's global thresholding.
    """
    gray = _to_grayscale(img)
    if method == "otsu":
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:  # adaptive (default)
        bw = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,
            C=8,
        )
    return bw
