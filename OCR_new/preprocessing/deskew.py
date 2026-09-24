"""
preprocessing/deskew.py
------------------------
Correct document skew (rotation caused by imperfect scanning).

Strategy
--------
1.  Convert to grayscale and binarise.
2.  Detect the dominant text-line angle using the Hough line transform.
3.  Rotate the image to correct the detected angle.

The implementation avoids any network calls — it is entirely local
OpenCV + NumPy.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

# Maximum rotation angle we attempt to correct (degrees on each side)
_MAX_SKEW_ANGLE: float = 45.0


def deskew(image: np.ndarray) -> np.ndarray:
    """
    Detect and correct the skew angle of *image*.

    Parameters
    ----------
    image : np.ndarray
        BGR or grayscale image.

    Returns
    -------
    np.ndarray
        Deskewed BGR (or grayscale) image of the same dtype.
    """
    angle = _detect_skew_angle(image)

    if abs(angle) < 0.1:
        log.debug("Skew angle %.2f° — no correction needed.", angle)
        return image

    log.debug("Correcting skew: %.2f°", angle)
    return _rotate(image, angle)


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────

def _detect_skew_angle(image: np.ndarray) -> float:
    """
    Estimate the skew angle of *image* in degrees.

    Uses a projection-profile approach:
    * Binarise the image with Otsu thresholding.
    * Scan angles in the range [-MAX, +MAX] with 0.5° resolution.
    * The angle that maximises the variance of horizontal pixel-sum
      projections corresponds to well-aligned text rows.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    h, w = binary.shape
    best_angle = 0.0
    best_variance = -1.0

    angles = [a * 0.5 for a in range(
        int(-_MAX_SKEW_ANGLE * 2),
        int(_MAX_SKEW_ANGLE * 2) + 1,
    )]

    for angle in angles:
        rad = math.radians(angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        # Rotate binary image around its centre
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(
            binary, M, (w, h),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        # Compute row-sum variance
        row_sums = np.sum(rotated, axis=1).astype(np.float64)
        variance = float(np.var(row_sums))

        if variance > best_variance:
            best_variance = variance
            best_angle = angle

    log.debug("Detected skew angle: %.2f° (variance=%.1f)", best_angle, best_variance)
    return best_angle


def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotate *image* by *angle* degrees, expanding the canvas to avoid cropping.
    """
    h, w = image.shape[:2]
    cx, cy = w / 2, h / 2

    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)

    # Compute new bounding dimensions
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)

    # Adjust translation
    M[0, 2] += (new_w / 2) - cx
    M[1, 2] += (new_h / 2) - cy

    # Background fill: white for documents
    border_value = (255, 255, 255) if image.ndim == 3 else 255

    rotated = cv2.warpAffine(
        image, M, (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
    return rotated
