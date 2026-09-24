"""
ocr_adapter.py — Frontend bridge to the OCR_new Document Intelligence engine.

services/ocr_service.py drives the Document Intake OCR flow through three
entry points:

    DocumentOCR().process(path)  -> {"raw_text", "confidence", "is_handwritten",
                                     "pages_processed", "fields",
                                     "department_suggestion", ...}
    extract_fields(text)         -> dict of extracted fields for plain text
    suggest_department(text)     -> {"suggested", "confidence", "scores"}

This module provides them on top of OCR_new's ``DocumentProcessor`` so the
service logic stays as it is.  The OCR itself (PaddleOCR, layout analysis,
text-type detection, entity + regex extraction) is done entirely by OCR_new;
this file only maps its ``DocumentResult`` onto the keys the service reads.

The backend reaches the same engine through backend/ocr_adapter.py.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_FE_DIR       = Path(__file__).resolve().parent.parent   # frontend/
_PROJECT_ROOT = _FE_DIR.parent                            # project root
_OCR_DIR      = _PROJECT_ROOT / "OCR_new"


def _ensure_ocr_new_on_path() -> None:
    """Make OCR_new's top-level packages (utils, ocr, document, ...) importable.

    OCR_new is inserted directly after the frontend directory: the frontend's
    own packages that share a name with an OCR_new folder (api, config, models)
    keep precedence, while OCR_new still resolves ahead of site-packages.
    """
    ocr_dir = str(_OCR_DIR)
    if ocr_dir in sys.path:
        return
    insert_at = len(sys.path)
    for i, entry in enumerate(sys.path):
        try:
            if Path(entry or os.getcwd()).resolve() == _FE_DIR:
                insert_at = i + 1
                break
        except (OSError, ValueError):
            continue
    sys.path.insert(insert_at, ocr_dir)


_ensure_ocr_new_on_path()

try:
    from document_intelligence import DocumentProcessor as _DocumentProcessor
    OCR_AVAILABLE = True
except Exception as exc:  # missing OCR_new folder or one of its dependencies
    _DocumentProcessor = None
    OCR_AVAILABLE = False
    logger.warning("OCR_new engine unavailable: %s", exc)


ENGINE_NAME = "OCR_new"

# One shared processor: OCR_new caches its PaddleOCR / NER / embedding models
# per DocumentProcessor instance, so creating one per call would reload them.
_processor = None
_init_lock = threading.Lock()
_run_lock  = threading.RLock()


def _get_processor():
    global _processor
    if not OCR_AVAILABLE:
        return None
    if _processor is None:
        with _init_lock:
            if _processor is None:
                # Load torch before PaddlePaddle to avoid the Windows DLL
                # conflict between the two (same as backend/ocr_adapter.py).
                try:
                    import torch  # noqa: F401
                except Exception:
                    pass
                _processor = _DocumentProcessor()
    return _processor


# ---------------------------------------------------------------------------
# Result mapping helpers
# ---------------------------------------------------------------------------

def _average_confidence(regions: List[Dict[str, Any]]) -> float:
    scores = [
        float(r["confidence"])
        for r in regions
        if isinstance(r.get("confidence"), (int, float))
    ]
    return sum(scores) / len(scores) if scores else 0.0


def _is_mostly_handwritten(regions: List[Dict[str, Any]]) -> bool:
    types = [r.get("text_type") for r in regions]
    return types.count("HANDWRITTEN") > types.count("PRINTED")


def _detect_director_instruction(regions: List[Dict[str, Any]]) -> Optional[str]:
    """Handwritten text that looks like a Director routing instruction.

    Same rule as backend/ocr_adapter.py, so a desktop intake flags the same
    documents the backend would.
    """
    for region in regions:
        if region.get("text_type") == "HANDWRITTEN":
            text = region.get("text", "").lower()
            if "director" in text and "to director" in text:
                continue  # Addressed to director
            instruction_verbs = ["send to", "forward to", "discuss", "approved", "speak", "hod", "fctd"]
            if any(v in text for v in instruction_verbs) or "director" in text:
                return region.get("text", "")
    return None


def _department_from_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the department OCR_new extracted (regex "department", then NER "departments")."""
    for key in ("department", "departments"):
        value = fields.get(key)
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v and str(v).strip():
                return {
                    "suggested":  str(v).strip(),
                    "confidence": None,
                    "scores":     {},
                    "source":     f"{ENGINE_NAME}:{key}",
                }
    return {"suggested": None, "confidence": 0.0, "scores": {}}


def _extract_text_fields(text: str) -> Dict[str, Any]:
    """Run OCR_new's entity + regex extraction on plain text.

    Mirrors the extraction step of DocumentProcessor.process(): NER fields
    first, then regex pattern fields that are not already present.
    """
    processor = _get_processor()
    if processor is None or not text or not text.strip():
        return {}

    fields: Dict[str, Any] = {}
    with _run_lock:
        try:
            ext_out = processor._get_entity_extractor().extract(text)
            fields.update(ext_out.get("extracted_fields", {}))
        except Exception as exc:
            logger.warning("OCR_new entity extraction failed: %s", exc)
        try:
            for field_name, res in processor._get_regex_engine().extract(text).items():
                val = res.value if hasattr(res, "value") else res
                if val is not None and field_name not in fields:
                    fields[field_name] = val
        except Exception as exc:
            logger.warning("OCR_new regex extraction failed: %s", exc)
    return fields


# ---------------------------------------------------------------------------
# Public API used by services/ocr_service.py
# ---------------------------------------------------------------------------

class DocumentOCR:
    """Runs OCR_new on a file and returns the dict shape ocr_service.py reads."""

    engine = ENGINE_NAME

    def process(self, file_path: str | Path) -> Dict[str, Any]:
        processor = _get_processor()
        if processor is None:
            raise RuntimeError("OCR_new engine is not available")

        try:
            with _run_lock:
                res = processor.process(str(file_path), mode="full")
        except SystemExit as exc:
            # OCR_new calls sys.exit() when its offline PaddleOCR models are
            # missing; turn that into a normal error so the intake form can
            # fall back instead of the worker thread dying silently.
            raise RuntimeError(
                "OCR_new stopped (PaddleOCR models not found?). "
                "Run 'python OCR_new/setup_models.py' once to install them."
            ) from exc

        regions = res.regions or []
        fields  = dict(res.extracted_fields or {})
        director_remark = _detect_director_instruction(regions)
        if director_remark is not None:
            fields["prior_director_review_detected"] = "true"
            fields["director_handwritten_remark"] = director_remark
        return {
            "file":                  str(Path(file_path).resolve()),
            "file_type":             res.source_type,
            "page_count":            res.pages,
            "pages_processed":       res.pages,
            "raw_text":              res.full_text or "",
            "confidence":            round(_average_confidence(regions), 4),
            "is_handwritten":        _is_mostly_handwritten(regions),
            "fields":                fields,
            "department_suggestion": _department_from_fields(fields),
            "classification":        res.classification or {},
            "engine":                ENGINE_NAME,
        }

    def _extract_fields(self, text: str) -> Dict[str, Any]:
        return extract_fields(text)

    def _suggest_department(self, text: str) -> Dict[str, Any]:
        return suggest_department(text)


def extract_fields(text: str) -> Dict[str, Any]:
    """Extract structured fields from plain text with OCR_new."""
    return _extract_text_fields(text)


def suggest_department(text: str) -> Dict[str, Any]:
    """Return the department OCR_new extracts from plain text, if any."""
    return _department_from_fields(_extract_text_fields(text))
