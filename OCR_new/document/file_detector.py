"""
document/file_detector.py
--------------------------
Detect the document type from a file path using both file extension and
MIME type inspection (magic bytes), so the correct processor is chosen.

Supported types
---------------
  IMAGE  – jpg, jpeg, png, tiff, tif, bmp, webp
  PDF    – pdf
  DOCX   – docx
  TEXT   – txt
  UNKNOWN
"""

from __future__ import annotations

import mimetypes
from enum import Enum, auto
from pathlib import Path

from utils.logger import get_logger

log = get_logger(__name__)


class DocumentType(Enum):
    IMAGE   = auto()
    PDF     = auto()
    DOCX    = auto()
    TEXT    = auto()
    UNKNOWN = auto()


# Extension → DocumentType mapping
_EXT_MAP: dict[str, DocumentType] = {
    ".jpg":  DocumentType.IMAGE,
    ".jpeg": DocumentType.IMAGE,
    ".png":  DocumentType.IMAGE,
    ".tiff": DocumentType.IMAGE,
    ".tif":  DocumentType.IMAGE,
    ".bmp":  DocumentType.IMAGE,
    ".webp": DocumentType.IMAGE,
    ".pdf":  DocumentType.PDF,
    ".docx": DocumentType.DOCX,
    ".txt":  DocumentType.TEXT,
}

# Magic-byte signatures (file header) for extra robustness
_MAGIC: dict[bytes, DocumentType] = {
    b"%PDF":              DocumentType.PDF,
    b"PK\x03\x04":       DocumentType.DOCX,   # ZIP-based (DOCX / XLSX / PPTX)
    b"\xff\xd8\xff":     DocumentType.IMAGE,   # JPEG
    b"\x89PNG":          DocumentType.IMAGE,   # PNG
    b"II*\x00":          DocumentType.IMAGE,   # TIFF (little-endian)
    b"MM\x00*":          DocumentType.IMAGE,   # TIFF (big-endian)
}


def detect(file_path: str | Path) -> DocumentType:
    """
    Determine the type of *file_path*.

    Strategy
    --------
    1. Extension lookup (fast and reliable for well-named files).
    2. Magic-byte inspection for ambiguous / incorrectly named files.
    3. MIME type sniffing as a final fallback.

    Parameters
    ----------
    file_path : str or Path

    Returns
    -------
    DocumentType
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    # --- 1. Extension ---------------------------------------------------
    ext = path.suffix.lower()
    if ext in _EXT_MAP:
        doc_type = _EXT_MAP[ext]
        log.debug("File type detected by extension: %s → %s", ext, doc_type.name)
        return doc_type

    # --- 2. Magic bytes -------------------------------------------------
    try:
        with open(path, "rb") as fh:
            header = fh.read(16)
        for magic, dtype in _MAGIC.items():
            if header.startswith(magic):
                log.debug(
                    "File type detected by magic bytes: %s → %s",
                    magic, dtype.name,
                )
                return dtype
    except OSError as exc:
        log.warning("Could not read file header: %s", exc)

    # --- 3. MIME type ---------------------------------------------------
    mime, _ = mimetypes.guess_type(str(path))
    if mime:
        if mime.startswith("image/"):
            return DocumentType.IMAGE
        if mime == "application/pdf":
            return DocumentType.PDF
        if mime in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            return DocumentType.DOCX
        if mime.startswith("text/"):
            return DocumentType.TEXT

    log.warning("Could not determine file type for: %s", path)
    return DocumentType.UNKNOWN
