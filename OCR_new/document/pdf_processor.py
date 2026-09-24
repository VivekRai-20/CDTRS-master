"""
document/pdf_processor.py
--------------------------
Convert PDF pages to images and yield them for OCR.

Supported PDF renderers (in priority order):
  1. pypdfium2  — self-contained fast Python PDF renderer (no external binaries needed!)
  2. pdf2image  — renders pages via Poppler if installed

Everything is local — no internet access at runtime.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from PIL import Image

from utils.logger import get_logger

log = get_logger(__name__)


def load_pdf_pages(
    file_path: str | Path,
    config: dict,
    temp_dir: str | Path | None = None,
) -> Iterator[tuple[int, np.ndarray]]:
    """
    Render each page of a PDF to a BGR image and yield (page, image) tuples.

    Parameters
    ----------
    file_path : str or Path
        Path to the PDF file.
    config : dict
        Full application config dict.
    temp_dir : str or Path, optional
        Directory for intermediate page images if needed.

    Yields
    ------
    (page: int, image: np.ndarray)
        page is 1-indexed.
        image is a BGR NumPy array.
    """
    path = Path(file_path)
    pdf_cfg = config.get("pdf", {})
    pre_cfg = config.get("preprocessing", {})

    dpi = int(pdf_cfg.get("dpi", pre_cfg.get("pdf_render_dpi", 300)))
    scale = dpi / 72.0  # standard PDF resolution is 72 pt/inch

    # Helper: try rendering page with PyMuPDF
    def _try_pymupdf_render(page_idx: int) -> np.ndarray | None:
        try:
            import pymupdf
            doc = pymupdf.open(str(path))
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            samples = np.frombuffer(pix.samples, dtype=np.uint8)
            if pix.n == 1:
                img = samples.reshape((pix.height, pix.width))
                bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif pix.n == 3:
                img = samples.reshape((pix.height, pix.width, 3))
                bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif pix.n == 4:
                img = samples.reshape((pix.height, pix.width, 4))
                bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            else:
                return None
            doc.close()
            return bgr
        except Exception as e:
            log.debug("PyMuPDF page render error on page %d: %s", page_idx + 1, e)
            return None

    # Helper: try extracting embedded image directly if available
    def _try_extract_embedded_image(page_idx: int) -> np.ndarray | None:
        try:
            import pymupdf
            doc = pymupdf.open(str(path))
            page = doc[page_idx]
            imgs = page.get_images(full=True)
            if imgs:
                xref = imgs[0][0]
                base_img = doc.extract_image(xref)
                raw_bytes = base_img.get("image")
                if raw_bytes:
                    nparr = np.frombuffer(raw_bytes, np.uint8)
                    decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if decoded is not None and decoded.std() >= 0.5:
                        doc.close()
                        return decoded
            doc.close()
        except Exception as e:
            log.debug("Embedded image extraction error on page %d: %s", page_idx + 1, e)
        return None

    # ── Strategy 1: pypdfium2 (Built-in, zero external binary dependency) ───
    try:
        import pypdfium2 as pdfium
        log.info("Rendering PDF via pypdfium2: %s (DPI=%d, scale=%.2f)", path.name, dpi, scale)
        pdf = pdfium.PdfDocument(str(path))
        num_pages = len(pdf)
        log.info("PDF has %d page(s).", num_pages)

        try:
            for page_idx in range(num_pages):
                page_num = page_idx + 1
                page = pdf[page_idx]
                pil_image = page.render(scale=scale).to_pil()
                page.close()
                
                # Convert PIL RGB to OpenCV BGR
                rgb_arr = np.array(pil_image.convert("RGB"))
                bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
                
                # Check for blank / solid render (e.g. corrupted PDF or missing fonts)
                if bgr_arr.std() < 0.5:
                    log.warning(
                        "Page %d rendered as a solid blank image (mean=%.1f). "
                        "Attempting PyMuPDF / embedded image fallback...",
                        page_num, float(bgr_arr.mean())
                    )
                    alt_bgr = _try_pymupdf_render(page_idx)
                    if alt_bgr is not None and alt_bgr.std() >= 0.5:
                        log.info("Page %d recovered via PyMuPDF renderer.", page_num)
                        bgr_arr = alt_bgr
                    else:
                        emb_bgr = _try_extract_embedded_image(page_idx)
                        if emb_bgr is not None and emb_bgr.std() >= 0.5:
                            log.info("Page %d recovered via direct embedded image extraction.", page_num)
                            bgr_arr = emb_bgr
                        else:
                            log.warning(
                                "Page %d remains blank after fallbacks. "
                                "The PDF page may be genuinely blank or unreadable.", page_num
                            )
                
                log.debug("Yielding page %d: shape=%s", page_num, bgr_arr.shape)
                yield page_num, bgr_arr
        finally:
            pdf.close()
        return
    except ImportError:
        log.debug("pypdfium2 not installed, falling back to PyMuPDF / pdf2image.")
    except Exception as exc:
        log.warning("pypdfium2 failed to render (%s), trying PyMuPDF / pdf2image fallback.", exc)

    # ── Strategy 2: PyMuPDF (fitz) ──────────────────────────────────────────
    try:
        import pymupdf
        log.info("Rendering PDF via PyMuPDF: %s (DPI=%d)", path.name, dpi)
        doc = pymupdf.open(str(path))
        num_pages = len(doc)
        log.info("PDF has %d page(s).", num_pages)
        try:
            for page_idx in range(num_pages):
                page_num = page_idx + 1
                bgr_arr = _try_pymupdf_render(page_idx)
                if bgr_arr is None or bgr_arr.std() < 0.5:
                    emb_bgr = _try_extract_embedded_image(page_idx)
                    if emb_bgr is not None:
                        bgr_arr = emb_bgr
                if bgr_arr is None:
                    # Provide empty fallback image rather than crash
                    bgr_arr = np.full((100, 100, 3), 255, dtype=np.uint8)
                yield page_num, bgr_arr
        finally:
            doc.close()
        return
    except ImportError:
        log.debug("PyMuPDF not installed, falling back to pdf2image.")
    except Exception as exc:
        log.warning("PyMuPDF failed to render (%s), trying pdf2image fallback.", exc)

    # ── Strategy 3: pdf2image (Requires Poppler binaries) ───────────────────
    try:
        from pdf2image import convert_from_path
        from pdf2image.exceptions import PDFInfoNotInstalledError
    except ImportError as exc:
        raise ImportError(
            "Neither pypdfium2, pymupdf, nor pdf2image is available.\n"
            "Install pypdfium2 or pymupdf: pip install pypdfium2 pymupdf"
        ) from exc

    paths_cfg = config.get("paths", {})
    fmt = pdf_cfg.get("page_image_format", "PNG").upper()
    keep_temp = pdf_cfg.get("keep_temp_pages", False)

    root = Path(__file__).resolve().parents[1]
    if temp_dir is None:
        temp_dir = root / paths_cfg.get("temp_dir", "temp")
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    poppler_path = pdf_cfg.get("poppler_path", None)
    kwargs = dict(dpi=dpi, fmt=fmt.lower(), output_folder=str(temp_dir), paths_only=True)
    if poppler_path:
        kwargs["poppler_path"] = str(poppler_path)

    log.info("Rendering PDF via pdf2image: %s (DPI=%d)", path.name, dpi)
    try:
        page_paths = convert_from_path(str(path), **kwargs)
    except PDFInfoNotInstalledError:
        raise EnvironmentError(
            "Poppler is not installed or not on PATH.\n"
            "Please install pypdfium2 (pip install pypdfium2) or configure Poppler."
        )
    except Exception as exc:
        raise RuntimeError(f"PDF rendering failed: {exc}") from exc

    log.info("PDF has %d page(s).", len(page_paths))

    try:
        for page_num, page_path in enumerate(page_paths, start=1):
            img = cv2.imread(str(page_path))
            if img is None:
                log.warning("Could not read rendered page %d: %s", page_num, page_path)
                continue
            yield page_num, img
    finally:
        if not keep_temp:
            for p in page_paths:
                try:
                    os.unlink(p)
                except OSError:
                    pass
