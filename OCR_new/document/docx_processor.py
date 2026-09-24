"""
document/docx_processor.py
---------------------------
Extract content from Word (.docx) documents for OCR.

Strategy
--------
1. Extract raw text paragraphs using python-docx (handles digital/typed text).
2. If the paragraph text is empty or the document is purely image-based,
   extract embedded images and yield them as pages for OCR.
3. Both paths produce (page_number, content) tuples — matching the interface
   of pdf_processor and image_processor.

Returns
-------
Two generators:
  load_docx_text_pages  → yields (page, text: str)
  load_docx_image_pages → yields (page, image: np.ndarray)

The OCR pipeline calls load_docx_image_pages when it needs OCR over
embedded/scanned content; load_docx_text_pages for native text.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from PIL import Image

from utils.logger import get_logger

log = get_logger(__name__)

# Supported image MIME types embedded in DOCX
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"}


def load_docx_text_pages(file_path: str | Path) -> Iterator[tuple[int, str]]:
    """
    Extract native (typed/digital) text from each paragraph in a DOCX.

    Yields
    ------
    (page: int, text: str)
        page numbers are approximated by section breaks / paragraph count.
        text is the paragraph content.
    """
    try:
        import docx
    except ImportError as exc:
        raise ImportError(
            "python-docx is required: pip install python-docx"
        ) from exc

    path = Path(file_path)
    log.info("Extracting text from DOCX: %s", path.name)

    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]

    log.info("Found %d non-empty paragraph(s).", len(paragraphs))

    # Approximate page grouping — yield entire doc as "page 1" of text
    # (python-docx does not expose page boundaries directly)
    full_text = "\n".join(paragraphs)
    if full_text.strip():
        yield 1, full_text


def load_docx_image_pages(
    file_path: str | Path,
    config: dict,
) -> Iterator[tuple[int, np.ndarray]]:
    """
    Extract embedded images from a DOCX and yield them as BGR frames.

    DOCX is a ZIP archive; images live under ``word/media/``.

    Yields
    ------
    (page: int, image: np.ndarray)
        page is 1-indexed (each embedded image gets its own page number).
    """
    path = Path(file_path)
    docx_cfg = config.get("docx", {})

    if not docx_cfg.get("extract_embedded_images", True):
        log.info("DOCX embedded image extraction disabled in config.")
        return

    log.info("Extracting embedded images from DOCX: %s", path.name)

    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            media_files = [
                n for n in zf.namelist()
                if n.startswith("word/media/")
                and Path(n).suffix.lower() in _IMAGE_EXTENSIONS
            ]

            log.info("Found %d embedded image(s).", len(media_files))

            for page_num, media_name in enumerate(sorted(media_files), start=1):
                try:
                    data = zf.read(media_name)
                    pil_img = Image.open(io.BytesIO(data))
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                    arr = np.array(pil_img, dtype=np.uint8)
                    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                    log.debug("Yielding embedded image %d: %s", page_num, media_name)
                    yield page_num, bgr
                except Exception as exc:
                    log.warning("Skipping embedded image %s: %s", media_name, exc)

    except zipfile.BadZipFile:
        raise ValueError(f"'{path}' is not a valid DOCX (ZIP) file.")
