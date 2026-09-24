"""
ocr_adapter.py — Frontend bridge to the OCR_new Document Intelligence engine.

services/ocr_service.py drives the Document Intake OCR flow through three
entry points:

    DocumentOCR().process(path)  -> {"raw_text", "confidence", "is_handwritten",
                                     "pages_processed", "fields",
                                     "department_suggestion", ...}
    extract_fields(text)         -> dict of extracted fields for plain text
    suggest_department(text)     -> {"suggested", "confidence", ...}

The OCR itself runs on the backend (POST /intelligence/analyze), which already
has OCR_new and its models loaded.  The desktop app therefore never loads
PaddleOCR / torch itself: the window stays responsive while a document is
read, memory is not doubled on a PC that also runs the server, and department
suggestions are matched against the real department list in the database.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ENGINE_NAME = "OCR_new"

#: The desktop app always has the server engine available (API mode); if the
#: server cannot read a file, process() raises and ocr_service falls back to
#: plain-text / digital-PDF extraction.
OCR_AVAILABLE = True

_text_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _repo():
    from repositories.provider import get_repository
    return get_repository()


def _analyze_text(text: str) -> Dict[str, Any]:
    """Server-side field extraction + routing suggestion for plain text.
    Cached per text so extract_fields() and suggest_department() cost one call."""
    if not text or not text.strip():
        return {}
    key = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
    with _cache_lock:
        if key in _text_cache:
            return _text_cache[key]
    try:
        result = _repo().analyze_intake_text(text) or {}
    except Exception as exc:
        logger.warning("Text analysis on the server failed: %s", exc)
        return {}
    with _cache_lock:
        if len(_text_cache) > 16:
            _text_cache.clear()
        _text_cache[key] = result
    return result


class DocumentOCR:
    """Runs OCR_new (on the server) on a file and returns the dict shape
    ocr_service.py reads."""

    engine = ENGINE_NAME

    def process(self, file_path: str | Path, body: str = "") -> Dict[str, Any]:
        result = _repo().analyze_intake_file(str(file_path), body=body or "") or {}
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "The server could not read this file.")

        suggestion = dict(result.get("department_suggestion") or {})
        employee = result.get("suggested_employee") or {}
        return {
            "file":                  str(Path(file_path).resolve()),
            "raw_text":              result.get("raw_text") or "",
            "confidence":            float(result.get("confidence") or 0.0),
            "is_handwritten":        bool(result.get("is_handwritten")),
            "pages_processed":       int(result.get("pages_processed") or 1),
            "page_count":            int(result.get("pages_processed") or 1),
            "fields":                dict(result.get("fields") or {}),
            "department_suggestion": suggestion,
            "suggested_employee":    employee.get("name"),
            "suggested_employee_id": employee.get("user_id"),
            "engine":                result.get("engine") or ENGINE_NAME,
        }

    def _extract_fields(self, text: str) -> Dict[str, Any]:
        return extract_fields(text)

    def _suggest_department(self, text: str) -> Dict[str, Any]:
        return suggest_department(text)


def extract_fields(text: str) -> Dict[str, Any]:
    """Structured fields for plain text (OCR_new entity + regex extraction)."""
    return dict(_analyze_text(text).get("fields") or {})


def suggest_department(text: str) -> Dict[str, Any]:
    """Best matching department for plain text, matched against the
    departments configured on the server."""
    result = _analyze_text(text)
    suggestion = dict(result.get("department_suggestion") or {})
    employee = result.get("suggested_employee") or {}
    if employee:
        suggestion.setdefault("suggested_employee", employee.get("name"))
        suggestion.setdefault("suggested_employee_id", employee.get("user_id"))
    return suggestion or {"suggested": None, "confidence": 0.0}
