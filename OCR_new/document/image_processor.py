"""
document/image_processor.py
----------------------------
Load and normalise image files for the OCR pipeline.

Returns a list of (page_number, np.ndarray) tuples so that every
document processor produces the same output shape, regardless of whether
the source is a single image, a multi-page TIFF, or a PDF page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from PIL import Image

from utils.logger import get_logger

log = get_logger(__name__)


def load_image_pages(
    file_path: str | Path,
) -> Iterator[tuple[int, np.ndarray]]:
    """
    Load an image file and yield (page_number, BGR ndarray) tuples.

    Supports single-frame images (JPG, PNG, BMP, WEBP) and multi-frame
    TIFF files.  Each frame is treated as one "page".

    Parameters
    ----------
    file_path : str or Path

    Yields
    ------
    (page: int, image: np.ndarray)
        page is 1-indexed.
        image is a BGR NumPy array (uint8).
    """
    path = Path(file_path)
    log.info("Loading image: %s", path.name)

    # Use Pillow to handle multi-frame TIFFs correctly
    try:
        pil_img = Image.open(path)
    except Exception as exc:
        raise OSError(f"Cannot open image file '{path}': {exc}") from exc

    frames: list[np.ndarray] = []

    try:
        # Iterate over all frames (multi-page TIFF)
        page_idx = 0
        while True:
            try:
                pil_img.seek(page_idx)
            except EOFError:
                break

            frame = _pil_to_bgr(pil_img)
            frames.append(frame)
            page_idx += 1
    except AttributeError:
        # seek() not available — single-frame image
        frames.append(_pil_to_bgr(pil_img))

    log.info("Image has %d frame(s).", len(frames))

    for i, frame in enumerate(frames, start=1):
        yield i, frame


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
    """Convert a Pillow Image to a BGR NumPy array."""
    # Ensure consistent colour space
    if pil_img.mode in ("RGBA", "LA"):
        # Composite onto a white background to flatten alpha channel
        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
        if pil_img.mode == "RGBA":
            bg.paste(pil_img, mask=pil_img.split()[3])
        else:
            bg.paste(pil_img, mask=pil_img.split()[1])
        pil_img = bg
    elif pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    arr = np.array(pil_img, dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
