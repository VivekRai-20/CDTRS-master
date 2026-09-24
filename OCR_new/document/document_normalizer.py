"""
document/document_normalizer.py
--------------------------------
Converts any supported document format into a common internal
``NormalizedDocument`` representation so the rest of the pipeline
does not need to know the original source format.

Internal representation
-----------------------
NormalizedDocument
    filename        str             – original filename
    source_format   str             – "PDF", "IMAGE", "DOCX", "TEXT", …
    pages           list[PageImage] – ordered list of page images
    metadata        dict            – any extra metadata (DPI, author, …)

PageImage
    page_number     int             – 1-indexed
    image           np.ndarray      – BGR image (OpenCV convention)
    metadata        dict            – per-page metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from document.file_detector import detect, DocumentType
from document.image_processor import load_image_pages
from document.pdf_processor import load_pdf_pages
from document.docx_processor import load_docx_image_pages
from utils.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PageImage:
    """One page of a document represented as a BGR image."""

    page_number: int
    image: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedDocument:
    """
    Common internal representation for any document type.

    All downstream pipeline stages (layout, OCR, semantic, …) receive
    a ``NormalizedDocument`` — they never need to handle PDFs or DOCX
    files directly.
    """

    filename: str
    source_format: str
    pages: list[PageImage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Convenience helpers                                                  #
    # ------------------------------------------------------------------ #

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def get_page(self, page_number: int) -> PageImage | None:
        """Return the PageImage with the given 1-indexed page_number."""
        for p in self.pages:
            if p.page_number == page_number:
                return p
        return None

    def __repr__(self) -> str:
        return (
            f"<NormalizedDocument filename='{self.filename}' "
            f"format='{self.source_format}' pages={self.page_count}>"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def normalize(file_path: str | Path, config: dict | None = None) -> NormalizedDocument:
    """
    Load and normalise *file_path* into a ``NormalizedDocument``.

    Parameters
    ----------
    file_path : str or Path
        Path to the input document.
    config : dict, optional
        Application configuration dict (from config.yaml).
        Required for PDF → image rendering (DPI, poppler path, …).

    Returns
    -------
    NormalizedDocument

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file type is not supported.
    """
    cfg = config or {}
    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Input document not found: {path}")

    doc_type = detect(path)
    log.info("Normalizing '%s' (type=%s)", path.name, doc_type.name)

    doc = NormalizedDocument(
        filename=path.name,
        source_format=doc_type.name,
        metadata={"source_path": str(path)},
    )

    if doc_type == DocumentType.IMAGE:
        _load_image(doc, path)

    elif doc_type == DocumentType.PDF:
        _load_pdf(doc, path, cfg)

    elif doc_type == DocumentType.DOCX:
        _load_docx(doc, path, cfg)

    elif doc_type == DocumentType.TEXT:
        _load_text(doc, path)

    else:
        raise ValueError(
            f"Unsupported document type '{doc_type.name}' for file: {path}"
        )

    log.info(
        "Normalized '%s': %d page(s)", path.name, doc.page_count
    )
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# Private loaders
# ──────────────────────────────────────────────────────────────────────────────

def _load_image(doc: NormalizedDocument, path: Path) -> None:
    """Load a single image (or multi-frame TIFF) as one page per frame."""
    for page_num, img in load_image_pages(path):
        doc.pages.append(PageImage(page_number=page_num, image=img))


def _load_pdf(doc: NormalizedDocument, path: Path, config: dict) -> None:
    """Render each PDF page to a BGR image."""
    for page_num, img in load_pdf_pages(path, config):
        doc.pages.append(PageImage(page_number=page_num, image=img))


def _load_docx(doc: NormalizedDocument, path: Path, config: dict) -> None:
    """
    Extract embedded images from a DOCX.

    Native text paragraphs are handled separately in the OCR pipeline
    (they don't need an image representation).
    """
    for page_num, img in load_docx_image_pages(path, config):
        doc.pages.append(PageImage(page_number=page_num, image=img))

    if not doc.pages:
        log.warning(
            "DOCX '%s' contained no embedded images. "
            "Native text extraction is handled by the OCR pipeline.",
            path.name,
        )


def _load_text(doc: NormalizedDocument, path: Path) -> None:
    """
    Plain-text files have no image.

    We create one synthetic PageImage with a blank 1×1 pixel image so the
    rest of the pipeline doesn't need special-casing; the OCR pipeline
    overrides this with native text handling.
    """
    blank = np.zeros((1, 1, 3), dtype=np.uint8)
    doc.pages.append(
        PageImage(
            page_number=1,
            image=blank,
            metadata={"native_text": path.read_text(encoding="utf-8", errors="replace")},
        )
    )
