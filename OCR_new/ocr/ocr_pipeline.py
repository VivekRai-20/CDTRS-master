"""
ocr/ocr_pipeline.py
--------------------
Orchestrates the full OCR pipeline for any supported document type.

Pipeline
--------
  File
   ↓ file_detector      (determine type)
   ↓ document/*         (load pages as BGR images)
   ↓ image_preprocessor (per-page preprocessing)
   ↓ OCR engine         (PaddleOCR → list of region dicts)
   ↓ return             (flat list of all region dicts)

The pipeline is intentionally decoupled from regex extraction — it only
produces structured OCR output.  The caller decides what to do with it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from document.file_detector import detect, DocumentType
from document.image_processor import load_image_pages
from document.pdf_processor import load_pdf_pages
from document.docx_processor import load_docx_text_pages, load_docx_image_pages
from ocr.base_engine import BaseOCREngine
from preprocessing.image_preprocessor import preprocess
from utils.logger import get_logger

log = get_logger(__name__)


class OCRPipeline:
    """
    Coordinates document loading, preprocessing, and OCR recognition.

    Parameters
    ----------
    engine : BaseOCREngine
        An already-initialised OCR engine.
    config : dict
        Full application config dict.
    """

    def __init__(self, engine: BaseOCREngine, config: dict) -> None:
        self.engine = engine
        self.config = config

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def process(self, file_path: str | Path) -> dict[str, Any]:
        """
        Run the full OCR pipeline on *file_path*.

        Parameters
        ----------
        file_path : str or Path

        Returns
        -------
        dict with keys:
            file        – absolute path (str)
            doc_type    – detected document type name
            pages       – total pages processed
            regions     – flat list of OCR region dicts
            full_text   – all region texts joined with newlines
            elapsed_s   – total wall-clock time in seconds
        """
        path = Path(file_path).resolve()
        log.info("="*60)
        log.info("Processing: %s", path.name)

        t_start = time.perf_counter()

        doc_type = detect(path)
        log.info("Document type: %s", doc_type.name)

        all_regions: list[dict[str, Any]] = []
        pages_processed = 0
        native_text_lines: list[str] = []

        # --- Route to the correct document handler --------------------- #

        if doc_type == DocumentType.IMAGE:
            for page, img in load_image_pages(path):
                regions = self._process_image(img, page)
                all_regions.extend(regions)
                pages_processed += 1

        elif doc_type == DocumentType.PDF:
            for page, img in load_pdf_pages(path, self.config):
                regions = self._process_image(img, page)
                all_regions.extend(regions)
                pages_processed += 1

        elif doc_type == DocumentType.DOCX:
            # 1. Native text paragraphs
            for page, text in load_docx_text_pages(path):
                if text.strip():
                    # Represent native text as a synthetic region
                    for line in text.splitlines():
                        if line.strip():
                            native_text_lines.append(line)
                            all_regions.append(
                                {
                                    "text":       line,
                                    "confidence": 1.0,
                                    "bbox":       [0, 0, 0, 0],
                                    "page":       page,
                                    "source":     "native_text",
                                }
                            )
                pages_processed += 1

            # 2. Embedded images (scanned content)
            for page, img in load_docx_image_pages(path, self.config):
                regions = self._process_image(img, page + 1000)
                all_regions.extend(regions)
                pages_processed += 1

        elif doc_type == DocumentType.TEXT:
            # Plain text — read and wrap in a region structure
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), start=1):
                if line.strip():
                    all_regions.append(
                        {
                            "text":       line,
                            "confidence": 1.0,
                            "bbox":       [0, 0, 0, 0],
                            "page":       1,
                            "source":     "plain_text",
                        }
                    )
            pages_processed = 1

        else:
            raise ValueError(f"Unsupported document type: {doc_type.name} ({path})")

        elapsed = time.perf_counter() - t_start
        full_text = self._build_full_text(all_regions)

        log.info(
            "Done: %d page(s), %d region(s) in %.2fs",
            pages_processed, len(all_regions), elapsed,
        )

        return {
            "file":      str(path),
            "doc_type":  doc_type.name,
            "pages":     pages_processed,
            "regions":   all_regions,
            "full_text": full_text,
            "elapsed_s": round(elapsed, 3),
        }

    @staticmethod
    def _build_full_text(regions: list[dict[str, Any]], line_tolerance: int = 15) -> str:
        """
        Merge regions on the same horizontal textline with a space,
        and separate different lines with newlines.
        """
        if not regions:
            return ""

        pages: dict[int, list[dict[str, Any]]] = {}
        for r in regions:
            pages.setdefault(r.get("page", 1), []).append(r)

        page_texts = []
        for page_num in sorted(pages.keys()):
            page_regions = pages[page_num]
            if not page_regions:
                continue

            if all(r.get("bbox") == [0, 0, 0, 0] for r in page_regions):
                page_texts.append("\n".join(r["text"] for r in page_regions if r.get("text", "").strip()))
                continue

            lines: list[list[dict[str, Any]]] = []
            for r in page_regions:
                bbox = r.get("bbox", [0, 0, 0, 0])
                y_mid = (bbox[1] + bbox[3]) / 2.0 if len(bbox) == 4 else 0

                placed = False
                for line in lines:
                    ref_bbox = line[0].get("bbox", [0, 0, 0, 0])
                    ref_y_mid = (ref_bbox[1] + ref_bbox[3]) / 2.0 if len(ref_bbox) == 4 else 0
                    ref_h = max(1, ref_bbox[3] - ref_bbox[1]) if len(ref_bbox) == 4 else 20
                    tol = max(line_tolerance, ref_h * 0.5)
                    if abs(y_mid - ref_y_mid) <= tol:
                        line.append(r)
                        placed = True
                        break
                if not placed:
                    lines.append([r])

            def line_y(line: list[dict[str, Any]]) -> float:
                b = line[0].get("bbox", [0, 0, 0, 0])
                return (b[1] + b[3]) / 2.0 if len(b) == 4 else 0

            lines.sort(key=line_y)

            formatted_lines = []
            for line in lines:
                line.sort(key=lambda r: (r.get("bbox", [0, 0, 0, 0])[0] if len(r.get("bbox", [])) == 4 else 0))
                line_str = " ".join(r["text"].strip() for r in line if r.get("text", "").strip())
                if line_str:
                    formatted_lines.append(line_str)

            page_texts.append("\n".join(formatted_lines))

        return "\n".join(page_texts)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _process_image(self, img: np.ndarray, page: int) -> list[dict[str, Any]]:
        """
        Run preprocessing followed by OCR on a single image array.
        If preprocessing fails, safely falls back to raw image.
        """
        try:
            preprocessed = preprocess(img, self.config)
        except Exception as exc:
            log.warning("Preprocessing failed on page %d: %s. Using raw image.", page, exc)
            preprocessed = img

        try:
            return self.engine.recognize(preprocessed, page=page)
        except Exception as exc:
            log.warning("OCR failed on preprocessed page %d (%s). Retrying with raw image...", page, exc)
            try:
                return self.engine.recognize(img, page=page)
            except Exception as exc2:
                log.error("OCR recognition completely failed on page %d: %s", page, exc2)
                return []
