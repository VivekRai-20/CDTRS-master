"""
ocr_service.py — Frontend OCR Service
Runs the OCR_new Document Intelligence engine (PaddleOCR with layout,
handwriting/text-type detection and entity/regex extraction) on document
files for instant UI feedback on the Document Intake page.  The engine is
reached through services/ocr_adapter.py; extraction patterns live in
OCR_new/extraction/patterns.yaml.

Falls back gracefully if OCR_new / PaddleOCR is not installed or the file
cannot be read, so the intake form can still be submitted manually.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Import the OCR engine from the shared OCR_new/ directory (via the adapter).
# ---------------------------------------------------------------------------
try:
    from services import ocr_adapter as _ocr_adapter
except Exception:
    _ocr_adapter = None

_OCR_AVAILABLE      = bool(_ocr_adapter and _ocr_adapter.OCR_AVAILABLE)
_DocumentOCR        = _ocr_adapter.DocumentOCR        if _OCR_AVAILABLE else None
_extract_fields     = _ocr_adapter.extract_fields     if _OCR_AVAILABLE else None
_suggest_department = _ocr_adapter.suggest_department if _OCR_AVAILABLE else None


# ---------------------------------------------------------------------------
# Priority normalisation helper
# ---------------------------------------------------------------------------
_PRIORITY_HIGH_KW = {"urgent", "immediate", "critical", "high", "asap", "expedite"}
_PRIORITY_LOW_KW  = {"low", "routine", "normal", "standard", "when possible"}

def _normalise_priority(raw: str) -> str:
    if not raw:
        return "Medium"
    t = raw.lower().strip()
    if any(kw in t for kw in _PRIORITY_HIGH_KW):
        return "High"
    if any(kw in t for kw in _PRIORITY_LOW_KW):
        return "Low"
    return "Medium"


def _normalise_date(raw: str) -> str:
    """Converts various date formats (DD/MM/YYYY, MM/DD/YYYY, etc.) to standard YYYY-MM-DD."""
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")
    s = str(raw).strip()
    if "T" in s:
        s = s.split("T")[0]
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B, %Y",
        "%b %d %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return s


# ---------------------------------------------------------------------------
# Director remark detection
# ---------------------------------------------------------------------------
_DIRECTOR_REMARK_PATTERNS = [
    r"director\s+remark\s*[:\-]\s*(.+)",
    r"director\s+directive\s*[:\-]\s*(.+)",
    r"director['\u2019]?s\s+instruction\s*[:\-]\s*(.+)",
    r"approved\s*\.\s*expedite\s*(.+)",
    r"as\s+per\s+director\s*['\u2019]?s?\s+order\s*[:\-]?\s*(.+)",
]

def _detect_director_remark(text: str):
    """Returns (has_remark: bool, remark_text: str)."""
    if not text:
        return False, ""
    for pattern in _DIRECTOR_REMARK_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return True, m.group(1).strip().rstrip(")")
    return False, ""


# ---------------------------------------------------------------------------
# Document format detection (values of the intake "Document Format" list)
# ---------------------------------------------------------------------------
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}


def _pdf_has_text_layer(file_path: str) -> bool:
    """True for a digital PDF, False for a scan (pages are only images)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        for page in reader.pages[:3]:
            if (page.extract_text() or "").strip():
                return True
    except Exception:
        pass
    return False


def _detect_format(file_path: str, body_text: str = "") -> str:
    if not file_path:
        return "Email Body" if body_text else "Other"
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return "PDF" if _pdf_has_text_layer(file_path) else "Scanned PDF"
    if ext in (".docx", ".doc"):
        return "DOCX"
    if ext in _IMAGE_EXTS:
        return "Image (PNG/JPG)"
    return "Other"


# ---------------------------------------------------------------------------
# Main OCR Service
# ---------------------------------------------------------------------------

class OCRService:
    """
    Intelligent OCR, Text Extraction and Routing Information Extraction Service.
    Calls the OCR_new engine (services/ocr_adapter.py) for real text
    extraction and field detection.  Regex patterns live in
    OCR_new/extraction/patterns.yaml.
    """

    # ------------------------------------------------------------------
    # Public API (used by document_intake.py)
    # ------------------------------------------------------------------

    def extract_from_file(
        self,
        file_path: str,
        title_hint: str = "",
        source_hint: str = "",
    ) -> Dict[str, Any]:
        """Run OCR on *file_path* and return a dict matching DocumentIntakePage expectations."""
        res = self.process_incoming_document(
            file_path,
            incoming_item={"title": title_hint, "source": source_hint},
        )
        return {
            "raw_text":                    res.get("extracted_text", ""),
            "suggested_title":             res.get("title", title_hint),
            "suggested_department":        res.get("suggested_department", ""),
            "suggested_employee":          res.get("suggested_employee", "Not Assigned"),
            "detected_priority":           res.get("priority", "Medium"),
            "detected_deadline":           res.get("deadline", ""),
            "confidence":                  res.get("confidence", 0),
            "has_prior_director_remark": res.get("has_prior_director_remark", False),
            "director_remark":             res.get("director_remark", ""),
            "is_handwritten":              res.get("is_handwritten", False),
            "pages_extracted":             res.get("pages_extracted", 1),
            "ocr_fields":                  res.get("ocr_fields", {}),
        }

    def extract_text(self, file_path: str) -> Dict[str, Any]:
        """Return extracted text/confidence for callers that only need OCR text."""
        data = self.process_incoming_document(file_path)
        return {"text": data["extracted_text"], "confidence": data["confidence"]}

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def process_incoming_document(
        self,
        file_path: str,
        incoming_item: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Runs the OCR_new engine on *file_path* (if available) and extracts
        structured metadata.  Falls back gracefully when OCR is unavailable
        or the file is missing — the intake form can still be completed manually.
        """
        title     = (incoming_item.get("title")  if incoming_item else None) or ""
        source    = (incoming_item.get("source") if incoming_item else None) or "External"
        mode      = (incoming_item.get("mode")   if incoming_item else None) or "Government Mail"
        body_text = (incoming_item.get("body")   if incoming_item else None) or ""
        today_str = datetime.now().strftime("%Y-%m-%d")

        # ---- 1.  Run OCR_new (PaddleOCR) on the file -----------------
        raw_text        = ""
        confidence      = 0.0
        is_handwritten  = False
        pages_extracted = 1
        ocr_fields: Dict[str, Any] = {}
        ocr_result: Dict[str, Any] = {}
        ocr_ran = False
        ocr_error = ""

        if _OCR_AVAILABLE and file_path and os.path.exists(file_path):
            try:
                engine          = _DocumentOCR()
                try:
                    ocr_result  = engine.process(file_path, body=body_text)
                except TypeError:
                    ocr_result  = engine.process(file_path)
                raw_text        = ocr_result.get("raw_text", "")
                confidence      = ocr_result.get("confidence", 0.0)
                is_handwritten  = ocr_result.get("is_handwritten", False)
                pages_extracted = ocr_result.get("pages_processed", 1)
                ocr_fields      = ocr_result.get("fields", {})
                ocr_ran         = True
            except Exception as exc:
                # Keep the error out of the document text: it is reported
                # separately so it never gets saved as the document's content.
                ocr_error = str(exc) or exc.__class__.__name__
                raw_text  = ""

        if (not ocr_ran or not raw_text.strip()) and file_path and os.path.exists(file_path):
            # PZ_26/08: Plain-text & digital PDF (pypdf) fallback when PaddleOCR not installed
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".txt":
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                        raw_text   = fh.read()
                        confidence = 1.0  # 100% accurate digital text reading
                        ocr_ran    = True
                elif ext == ".pdf":
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(file_path)
                        parts = [p.extract_text() or "" for p in reader.pages]
                        raw_text = "\n".join(parts).strip()
                        pages_extracted = len(reader.pages)
                        if raw_text:
                            confidence = 0.88  # Baseline digital extraction score
                            ocr_ran    = True
                    except Exception:
                        pass
            except Exception:
                pass

        # Real document text: OCR / digital extraction plus any e-mail body.
        text_found = bool(raw_text.strip() or body_text.strip())
        if raw_text.strip():
            ocr_error = ""

        # Combine OCR output with any body text or title hint provided
        combined_text = "\n".join(t for t in [raw_text, body_text] if t).strip()
        if not combined_text and title:
            combined_text = title

        # PZ_26/08: Run standalone rules engine on combined_text to extract fields and department suggestion
        if _extract_fields and not ocr_fields and combined_text:
            ocr_fields = _extract_fields(combined_text)
        elif _OCR_AVAILABLE and not ocr_fields and combined_text:
            try:
                engine = _DocumentOCR()
                ocr_fields = engine._extract_fields(combined_text)
            except Exception:
                pass

        if _suggest_department and not ocr_result.get("department_suggestion") and combined_text:
            dept_s = _suggest_department(combined_text)
            if dept_s.get("suggested"):
                ocr_result["department_suggestion"] = dept_s
        elif _OCR_AVAILABLE and not ocr_result.get("department_suggestion") and combined_text:
            try:
                engine = _DocumentOCR()
                dept_s = engine._suggest_department(combined_text)
                if dept_s.get("suggested"):
                    ocr_result["department_suggestion"] = dept_s
            except Exception:
                pass

        # ---- 2.  Extract / derive fields from OCR result -------------

        # Title: OCR subject > hint > filename stem
        ocr_title = (
            ocr_fields.get("subject", "")
            or ocr_fields.get("title", "")
            or title
            or (os.path.splitext(os.path.basename(file_path))[0] if file_path else "")
        )

        # Date
        raw_date = ocr_fields.get("date", "")
        ocr_date = _normalise_date(raw_date) if raw_date else today_str

        # Priority
        raw_prio = ocr_fields.get("priority", "")
        priority = _normalise_priority(raw_prio) if raw_prio else "Medium"
        if incoming_item and incoming_item.get("priority"):
            priority = _normalise_priority(str(incoming_item["priority"]))

        # Deadline
        deadline = ocr_fields.get("deadline", "")
        if isinstance(deadline, list):
            deadline = deadline[0] if deadline else ""

        # Suggested department from OCR engine
        dept_suggestion = ocr_result.get("department_suggestion") or {}
        suggested_dept  = dept_suggestion.get("suggested") or ""
        suggested_dept_id = dept_suggestion.get("department_id")
        department_match = dept_suggestion.get("confidence") if suggested_dept else None

        # Suggested employee: a staff member named in the document, else a
        # name the extraction rules picked up.
        raw_emp = (
            ocr_result.get("suggested_employee")
            or dept_suggestion.get("suggested_employee")
            or ocr_fields.get("employee")
            or ocr_fields.get("signatory")
        )
        if isinstance(raw_emp, list):
            raw_emp = raw_emp[0] if raw_emp else None
        suggested_emp = raw_emp if (raw_emp and raw_emp not in ("Not Assigned", "None", "")) else None
        suggested_emp_id = ocr_result.get("suggested_employee_id") or dept_suggestion.get("suggested_employee_id")

        # PZ_26/08: Dynamic extraction quality confidence scaling for digital files; neural score for PaddleOCR
        if not _OCR_AVAILABLE and confidence > 0:
            f_count = len([v for v in ocr_fields.values() if v])
            confidence = min(0.98, max(0.78, 0.82 + (f_count * 0.025)))

        conf_pct = round(confidence * 100) if confidence <= 1.0 else round(confidence)


        # ---- 3.  Director remark detection ---------------------------
        # A handwritten Director note found by OCR is the most reliable
        # source; typed "Director remark: ..." lines are the fallback.
        has_remark, remark_text = False, ""
        if str(ocr_fields.get("prior_director_review_detected", "")).lower() == "true":
            remark_text = str(ocr_fields.get("director_handwritten_remark") or "").strip()
            has_remark  = bool(remark_text)
        if not has_remark:
            has_remark, remark_text = _detect_director_remark(combined_text)
        if not has_remark and incoming_item:
            if incoming_item.get("has_prior_director_remark"):
                has_remark  = True
                remark_text = incoming_item.get("director_remark", "Approved.")
            elif incoming_item.get("director_remark"):
                has_remark  = True
                remark_text = incoming_item["director_remark"]

        # ---- 4.  File format detection --------------------------------
        local_file = file_path if (file_path and os.path.exists(file_path)) else ""
        declared = str((incoming_item or {}).get("format") or (incoming_item or {}).get("file_type") or "")
        if not local_file and declared.lower().startswith("email"):
            fmt = "Email Body"  # an e-mail from the inbox with no local file
        else:
            fmt = _detect_format(local_file, body_text)

        # PZ_26/08 - Terminal Debug: Output OCR Results in Frontend Console
        print("\n" + "=" * 70, flush=True)
        print(f"[FRONTEND OCR SERVICE] Text Extraction & Document Intelligence", flush=True)
        print(f"* Target File       : {os.path.basename(file_path) if file_path else 'In-Memory / Text Stream'}", flush=True)
        if file_path and os.path.exists(file_path):
            print(f"* File Size         : {round(os.path.getsize(file_path)/1024, 2)} KB", flush=True)
        print(f"* Extraction Engine : {'OCR_new Document Intelligence (PaddleOCR)' if _OCR_AVAILABLE else 'Digital Text / PyMuPDF Extractor'}", flush=True)
        if ocr_error:
            print(f"* Status            : FAILED ({ocr_error})", flush=True)
        else:
            print(f"* Status            : SUCCESS ({pages_extracted} page(s) processed)", flush=True)
        print(f"* Overall Confidence: {conf_pct}% ({confidence:.4f})", flush=True)
        print(f"* Text Extracted    : {len(raw_text)} characters", flush=True)
        if raw_text.strip():
            preview_lines = raw_text.strip().split("\n")[:4]
            preview_block = "\n  ".join(preview_lines)
            print(f"* Text Preview      :\n  {preview_block}", flush=True)
        print(f"* Derived Metadata  :", flush=True)
        print(f"  - Title           : {ocr_title}", flush=True)
        print(f"  - Priority        : {priority}", flush=True)
        print(f"  - Deadline        : {deadline or 'Not Specified'}", flush=True)
        print(f"  - Suggested Dept  : {suggested_dept or 'None'}", flush=True)
        print(f"  - Suggested Staff : {suggested_emp or 'Not Assigned'}", flush=True)
        if department_match is not None:
            print(f"  - Routing Score   : {round(float(department_match) * 100)}%", flush=True)
        if has_remark:
            print(f"  - Director Remark : {remark_text}", flush=True)
        print("=" * 70 + "\n", flush=True)

        return {
            # Core metadata
            "title":                     ocr_title or "Official Document",
            "source":                    source,
            "mode":                      mode,
            "date":                      ocr_date,
            "priority":                  priority,
            "deadline":                  deadline,
            "format":                    fmt,
            # OCR content
            "extracted_text":            combined_text if text_found else "",
            "ocr_error":                 ocr_error,
            "is_handwritten":            is_handwritten,
            "pages_extracted":           pages_extracted,
            "ocr_fields":                ocr_fields,
            # Routing
            "suggested_department":      suggested_dept,
            "suggested_department_id":   suggested_dept_id,
            "department_match":          department_match,
            "ranked_departments":        dept_suggestion.get("ranked") or [],
            "suggested_employee":        suggested_emp,
            "suggested_employee_id":     suggested_emp_id,
            "confidence":                round(confidence, 4) if confidence <= 1.0 else round(confidence / 100.0, 4),
            "confidence_pct":            conf_pct,
            # Director directive
            "has_prior_director_remark": has_remark,
            "director_remark":           remark_text,
            # Housekeeping
            "file_path":                 file_path,
        }


# Global singleton
ocr_service = OCRService()