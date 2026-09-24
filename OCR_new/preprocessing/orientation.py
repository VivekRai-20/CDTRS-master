"""
preprocessing/orientation.py
-----------------------------
Auto-detect and correct page orientation (0°, 90°, 180°, 270°).

Strategy
--------
1.  Primary   – Use Tesseract OSD (Orientation and Script Detection) when
                Tesseract is installed.  This is the most reliable approach.
2.  Fallback  – Heuristic based on text-region aspect ratios detected by
                OpenCV contour analysis.  No external tools required.

The module never downloads anything.
"""

from __future__ import annotations

import subprocess
import shutil

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

# Allowed correction angles
_VALID_ANGLES = {0, 90, 180, 270}


def fix_orientation(image: np.ndarray, config: dict | None = None) -> np.ndarray:
    """
    Detect and correct the page orientation of *image*.

    Parameters
    ----------
    image : np.ndarray
        BGR document image.
    config : dict, optional
        Full application config.

    Returns
    -------
    np.ndarray
        Orientation-corrected BGR image.
    """
    angle = _detect_orientation_angle(image, config or {})

    if angle == 0:
        log.debug("Orientation: no correction needed (0°).")
        return image

    log.debug("Correcting orientation: rotating by %d°", angle)
    return _rotate_fixed(image, angle)


# ──────────────────────────────────────────────────────────────────────────────
# Detection strategies
# ──────────────────────────────────────────────────────────────────────────────

def _detect_orientation_angle(image: np.ndarray, config: dict) -> int:
    """
    Return the number of degrees to rotate the image clockwise so that
    it is correctly oriented.  Returns 0 if already correct.
    """
    # --- 1. Tesseract OSD (preferred) ---
    if shutil.which("tesseract") is not None:
        angle = _tesseract_osd(image)
        if angle is not None:
            return angle

    # --- 2. Heuristic fallback ---
    return _heuristic_orientation(image)


def _tesseract_osd(image: np.ndarray) -> int | None:
    """
    Run ``tesseract --psm 0`` (OSD only) and parse the rotation angle.

    Returns None if Tesseract is unavailable or OSD fails.
    """
    try:
        import tempfile, os
        from pathlib import Path

        # Write image to a temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        cv2.imwrite(tmp_path, image)

        result = subprocess.run(
            ["tesseract", tmp_path, "stdout", "--psm", "0", "-l", "osd"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        os.unlink(tmp_path)

        for line in result.stdout.splitlines():
            if line.startswith("Rotate:"):
                angle = int(line.split(":")[1].strip())
                if angle in _VALID_ANGLES:
                    log.debug("Tesseract OSD reports rotation: %d°", angle)
                    return angle

    except Exception as exc:
        log.debug("Tesseract OSD failed: %s", exc)

    return None


def _heuristic_orientation(image: np.ndarray) -> int:
    """
    Very simple heuristic: count text-like contours and check if more
    contours are horizontal (portrait) or vertical (landscape).

    Returns 0 or 90.  Cannot detect 180° without Tesseract.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h_count = 0  # wider-than-tall (likely horizontal text)
    v_count = 0  # taller-than-wide (likely vertical text)

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 5 or h < 5:
            continue
        if w > h:
            h_count += 1
        else:
            v_count += 1

    if v_count > h_count * 1.5:
        log.debug("Heuristic: majority vertical contours → rotating 90°")
        return 90

    log.debug("Heuristic: orientation appears correct (0°)")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Rotation helper
# ──────────────────────────────────────────────────────────────────────────────

def _rotate_fixed(image: np.ndarray, angle: int) -> np.ndarray:
    """
    Rotate *image* by an exact multiple of 90°.

    Parameters
    ----------
    angle : int
        Clockwise rotation in degrees (90, 180, or 270).
    """
    if angle == 90:
        # Counter-clockwise 90° == clockwise 270°
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image
