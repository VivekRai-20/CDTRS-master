"""Document intelligence: OCR extraction and advisory routing suggestions.

Both are ASSISTIVE only.  OCR fills in fields the DS can correct, and the
routing suggestion is a hint the DS may apply, edit or ignore.  Nothing in
this module routes a document or changes workflow state by itself.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import models
from models import AttachmentType, OCRStatus, RoutingSource

# ---------------------------------------------------------------------------
# Make the OCR_new engine (via backend/ocr_adapter.py) importable whether the
# backend runs from the project root or from backend/.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OCR_DIR = _PROJECT_ROOT / "OCR_new"
if str(_OCR_DIR) not in sys.path:
    sys.path.insert(0, str(_OCR_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from backend.ocr_adapter import ocr_adapter
    _OCR_AVAILABLE = True
except Exception as e:
    ocr_adapter = None
    _OCR_AVAILABLE = False
    print(f'OCR Adapter load failed: {e}')


def _ocr_engine_ready() -> bool:
    return bool(_OCR_AVAILABLE and ocr_adapter is not None and ocr_adapter.processor)


def _store_extracted_fields(db: Session, doc_id: int, fields: Optional[Dict[str, Any]]) -> None:
    """Save OCR-extracted fields as unverified values.

    A field the DS already verified keeps its verified value; only the raw
    extracted value is refreshed.
    """
    existing = {
        f.field_name: f
        for f in db.query(models.DocumentExtractedField).filter(
            models.DocumentExtractedField.document_id == doc_id
        ).all()
    }
    for fname, fval in (fields or {}).items():
        if isinstance(fval, (list, tuple, set)):
            fval = ", ".join(str(v) for v in fval if v not in (None, ""))
        if fval is None or not str(fval).strip():
            continue
        name = str(fname).upper()[:100]
        row = existing.get(name)
        if row is not None:
            row.extracted_value = str(fval)
        else:
            row = models.DocumentExtractedField(
                document_id=doc_id,
                field_name=name,
                extracted_value=str(fval),
            )
            db.add(row)
            existing[name] = row



# ---------------------------------------------------------------------------
# Department matching (advisory)
#
# Two signals are combined:
#   * keyword  - the department's name / code / staff roles appear in the text,
#                or OCR extracted a "Department: ..." line naming it;
#   * semantic - similarity of the text to a short department profile, using
#                OCR_new's local embedding model.
# score = 1 - (1 - keyword) * (1 - semantic): either signal alone can carry a
# match, and both together strengthen it.
# ---------------------------------------------------------------------------

#: Below this combined score no department is suggested.
MIN_DEPARTMENT_SCORE = 0.3
#: Semantic similarity alone (no keyword evidence) must reach this to suggest
#: a department: ordinary office wording is ~0.2-0.35 similar to everything.
MIN_SEMANTIC_ONLY = 0.4


def _is_confident_match(item: Optional[Dict[str, Any]]) -> bool:
    if not item or item.get("score", 0.0) < MIN_DEPARTMENT_SCORE:
        return False
    return item.get("keyword", 0.0) >= 0.2 or item.get("semantic", 0.0) >= MIN_SEMANTIC_ONLY

_DEPT_STOPWORDS = {
    "and", "of", "the", "for", "department", "dept", "division", "section",
    "office", "unit", "cell", "wing", "branch", "services", "service", "team",
}


# Typical subject matter of common office departments.  A department picks up
# a topic when its name / code contains one of the topic's trigger words, so
# this works for whatever departments are configured (the same idea as the
# old OCR rules' department keywords, but not tied to fixed department names).
_TOPIC_LEXICON = [
    ({"finance", "financial", "account", "accounts", "budget", "treasury", "fin", "audit", "payroll"},
     ["salary", "salaries", "payment", "payments", "budget", "invoice", "bill", "bills", "reimbursement",
      "expenditure", "audit", "funds", "fund", "arrears", "pension", "gst", "tax", "tds", "voucher",
      "sanction", "grant", "allowance", "advance", "refund", "ledger", "accounts"]),
    ({"talent", "hr", "human", "personnel", "establishment", "recruitment", "staff", "training"},
     ["recruitment", "appointment", "interview", "leave", "transfer", "promotion", "joining", "resignation",
      "retirement", "training", "posting", "deputation", "disciplinary", "attendance", "vacancy",
      "candidate", "candidates", "increment"]),
    ({"information", "it", "tech", "computer", "computers", "systems", "digital", "network",
      "software", "ict", "electronics"},
     ["network", "server", "servers", "software", "hardware", "computer", "computers", "laptop", "laptops",
      "email", "internet", "website", "portal", "database", "cyber", "antivirus", "firewall", "backup",
      "printer", "connectivity", "wifi", "login", "password"]),
    ({"procurement", "purchase", "purchases", "stores", "store", "supply", "supplies", "material",
      "materials", "operations", "logistics", "ops"},
     ["purchase", "procurement", "tender", "tenders", "quotation", "quotations", "vendor", "vendors",
      "supplier", "supply", "stores", "stock", "inventory", "gem", "bid", "bids", "contract"]),
    ({"administration", "admin", "administrative", "general", "estate", "corp", "facilities", "support"},
     ["maintenance", "repair", "vehicle", "building", "housekeeping", "security", "stationery", "furniture",
      "electricity", "canteen", "accommodation", "premises", "cleaning", "guest"]),
    ({"legal", "law", "vigilance"},
     ["court", "legal", "case", "petition", "notice", "hearing", "advocate", "affidavit", "rti", "complaint",
      "vigilance", "inquiry", "judgment"]),
    ({"research", "rnd", "science", "scientific", "lab", "laboratory"},
     ["research", "study", "proposal", "project", "publication", "experiment", "laboratory", "patent",
      "prototype", "innovation", "collaboration", "journal"]),
    ({"customer", "customers", "client", "clients", "public", "grievance", "relations", "experience",
      "helpdesk", "citizen"},
     ["complaint", "complaints", "grievance", "customer", "client", "feedback", "query", "queries",
      "citizen", "helpdesk"]),
    ({"engineering", "engineer", "works", "technical", "civil", "electrical", "mechanical"},
     ["engineering", "design", "construction", "installation", "technical", "specification", "drawing",
      "estimate", "works", "commissioning", "equipment"]),
    ({"executive", "director", "directorate", "secretariat", "management", "chairman", "ceo"},
     ["meeting", "minutes", "board", "policy", "agenda", "directive"]),
    ({"marketing", "market", "business", "sales", "partnership", "partnerships", "strategy"},
     ["market", "marketing", "sales", "partner", "partnership", "mou", "agreement", "customer", "strategy",
      "business", "promotion", "brand"]),
]


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _tokens(value: Any) -> List[str]:
    return [t for t in _norm_text(value).split() if t != "and"]


def _significant(tokens: List[str]) -> List[str]:
    return [t for t in tokens if t not in _DEPT_STOPWORDS and len(t) >= 3]


def _phrase_in(phrase_tokens: List[str], text_tokens: List[str]) -> bool:
    if not phrase_tokens:
        return False
    n = len(phrase_tokens)
    return any(text_tokens[i:i + n] == phrase_tokens for i in range(len(text_tokens) - n + 1))


def _token_found(token: str, text_token_set: set, text_prefixes: set) -> bool:
    if token in text_token_set:
        return True
    # "procurement" ~ "procure", "accounts" ~ "accounting"
    return len(token) >= 6 and token[:6] in text_prefixes


def _department_profiles(db: Session, depts: List[models.Department]) -> Dict[int, str]:
    """Short description of each department for semantic matching: its name,
    code and the roles of the staff who work there."""
    roles: Dict[int, List[str]] = {}
    for emp in get_employees(db):
        if emp.department_id and emp.designation:
            bucket = roles.setdefault(emp.department_id, [])
            if emp.designation not in bucket and len(bucket) < 8:
                bucket.append(emp.designation)
    profiles = {}
    for d in depts:
        text = f"Department: {d.name}"
        if d.code:
            text += f" ({d.code})"
        description = (getattr(d, "description", None) or "").strip()
        if description:
            text += f". Description: {description}"
        keywords = (getattr(d, "keywords", None) or "").strip()
        if keywords:
            text += f". Keywords: {keywords}"
        topics = [t for t in _department_topics(d) if t not in keywords.lower()]
        if topics:
            text += ". Handles: " + ", ".join(topics[:15])
        if roles.get(d.id):
            text += ". Staff roles: " + ", ".join(roles[d.id])
        profiles[d.id] = text
    return profiles


def _extracted_department_names(fields: Optional[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    for key, value in (fields or {}).items():
        if str(key).lower() not in ("department", "departments", "dept"):
            continue
        values = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
        names.extend(str(v).strip() for v in values if str(v or "").strip())
    return names


def _department_keywords(dept: models.Department) -> List[List[str]]:
    """The routing keywords an administrator configured for the department
    (Admin > Department Configuration), each as a list of tokens."""
    raw = getattr(dept, "keywords", None) or ""
    phrases: List[List[str]] = []
    for part in re.split(r"[,;\n]+", raw):
        tokens = _tokens(part)
        if tokens and tokens not in phrases:
            phrases.append(tokens)
    return phrases


def _keyword_found(phrase: List[str], text_tokens: List[str], text_token_set: set,
                   text_prefixes: set, raw_text: str) -> bool:
    if len(phrase) > 1:
        return _phrase_in(phrase, text_tokens)
    token = phrase[0]
    if len(token) <= 3:
        # Short words ("IT", "HR", "GST") only count as a whole word written
        # in capitals, so ordinary words such as "it" do not match.
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(token.upper())}(?![A-Za-z0-9])", raw_text) is not None
    return _token_found(token, text_token_set, text_prefixes)


def _department_topics(dept: models.Department) -> List[str]:
    """Topic keywords for a department, chosen from its name, code and
    description."""
    name_tokens = set(_tokens(dept.name)) | set(_tokens(dept.code))
    name_tokens |= set(_significant(_tokens(getattr(dept, "description", None) or "")))
    keywords: List[str] = []
    for triggers, words in _TOPIC_LEXICON:
        if name_tokens & triggers:
            keywords.extend(w for w in words if w not in keywords)
    return keywords


def _keyword_score(dept: models.Department, text_tokens: List[str], text_token_set: set,
                   text_prefixes: set, raw_text: str, extracted: List[List[str]]) -> float:
    name_tokens = _tokens(dept.name)
    score = 0.0
    if _phrase_in(name_tokens, text_tokens):
        score = 1.0
    code = (dept.code or "").strip()
    if code and len(code) >= 2 and re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", raw_text):
        # Codes are matched case-sensitively ("IT", "HR") to avoid ordinary
        # words; two-letter codes still occur in all-caps headings, so they
        # count for less.
        score = max(score, 0.8 if len(code) > 2 else 0.5)
    significant = _significant(name_tokens)
    if significant:
        found = sum(1 for t in significant if _token_found(t, text_token_set, text_prefixes))
        if found == len(significant):
            score = max(score, 0.85)  # every word of the name, any order
        else:
            score = max(score, 0.5 * found / len(significant))
    topics = _department_topics(dept)
    if topics:
        hits = sum(1 for w in topics if w in text_token_set)
        score = max(score, (0.0, 0.2, 0.45, 0.65)[hits] if hits < 4 else 0.8)
    # Keywords configured for this department count for more than the
    # generic topic words: they were chosen for this organisation.
    configured = _department_keywords(dept)
    if configured:
        hits = sum(
            1 for phrase in configured
            if _keyword_found(phrase, text_tokens, text_token_set, text_prefixes, raw_text)
        )
        if hits:
            score = max(score, (0.0, 0.55, 0.75)[hits] if hits < 3 else 0.9)
    for ext in extracted:
        ext_sig = _significant(ext)
        if not ext_sig or not significant:
            continue
        overlap = len(set(ext_sig) & set(significant))
        if overlap == len(significant) or overlap == len(ext_sig):
            score = max(score, 0.95)
        elif overlap:
            score = max(score, 0.6 * overlap / len(significant))
    return min(1.0, score)


def find_mentioned_employee(db: Session, text: str) -> Optional[models.Employee]:
    """An active employee whose full name appears in the text."""
    text_lower = (text or "").lower()
    if not text_lower:
        return None
    best = None
    for emp in get_employees(db):
        name = (emp.full_name or "").strip().lower()
        if len(name) > 3 and name in text_lower:
            if best is None or len(name) > len(best.full_name or ""):
                best = emp
    return best


def rank_departments(
    db: Session,
    text: str,
    fields: Optional[Dict[str, Any]] = None,
    depts: Optional[List[models.Department]] = None,
) -> List[Dict[str, Any]]:
    """Every active department scored against the document, best first.

    Each item: {"department", "department_id", "score", "keyword", "semantic"}.
    """
    depts = depts if depts is not None else get_departments(db)
    text = text or ""
    if not depts or not text.strip():
        return []

    text_tokens = _tokens(text)
    text_token_set = set(text_tokens)
    text_prefixes = {t[:6] for t in text_tokens if len(t) >= 6}
    extracted = [_tokens(n) for n in _extracted_department_names(fields)]

    semantic: Dict[int, float] = {}
    if _ocr_engine_ready():
        profiles = _department_profiles(db, depts)
        ref_texts = [profiles[d.id] for d in depts]
        by_ref = {profiles[d.id]: d.id for d in depts}
        try:
            for item in ocr_adapter.rank_references(text, ref_texts):
                dept_id = by_ref.get(item["reference"])
                if dept_id is not None:
                    semantic[dept_id] = max(0.0, min(1.0, float(item["similarity"])))
        except Exception as e:
            print(f"Semantic matching failed: {e}")

    employee = find_mentioned_employee(db, text)

    ranked = []
    for d in depts:
        kw = _keyword_score(d, text_tokens, text_token_set, text_prefixes, text, extracted)
        if employee is not None and employee.department_id == d.id:
            kw = max(kw, 0.6)
        sem = semantic.get(d.id, 0.0)
        combined = 1.0 - (1.0 - kw) * (1.0 - sem)
        ranked.append({
            "department": d.name,
            "department_id": d.id,
            "score": round(combined, 4),
            "keyword": round(kw, 4),
            "semantic": round(sem, 4),
        })
    ranked.sort(key=lambda r: (r["score"], r["keyword"]), reverse=True)
    return ranked


def suggest_routing_for_text(
    db: Session,
    text: str,
    fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Department (and staff member) suggestion for text read from a document."""
    ranked = rank_departments(db, text, fields)
    best = ranked[0] if ranked and _is_confident_match(ranked[0]) else None
    employee = find_mentioned_employee(db, text)
    return {
        "department_suggestion": {
            "suggested": best["department"] if best else None,
            "department_id": best["department_id"] if best else None,
            "confidence": best["score"] if best else 0.0,
            "score": best["score"] if best else None,
            "ranked": ranked[:5],
        },
        "suggested_employee": (
            {
                "user_id": employee.user_id,
                "name": employee.full_name,
                "department_id": employee.department_id,
            }
            if employee is not None else None
        ),
    }


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def analyze_document_file(db: Session, file_path: str, extra_text: str = "") -> Dict[str, Any]:
    """OCR a file that is not registered yet (desktop intake) and suggest where
    it should go.  Nothing is stored."""
    if not _ocr_engine_ready():
        return {"success": False, "error": "The OCR engine is not available on the server."}
    res = ocr_adapter.process(file_path)
    if not res.get("success"):
        return {"success": False, "error": res.get("error") or "OCR failed."}
    text = res.get("text") or ""
    fields = _json_safe(res.get("extracted_fields") or {})
    combined = "\n".join(t for t in (text, extra_text or "") if t).strip()
    result = {
        "success": True,
        "engine": res.get("engine") or "OCR_new",
        "raw_text": text,
        "confidence": res.get("confidence") or 0.0,
        "is_handwritten": bool(res.get("is_handwritten")),
        "pages_processed": int(res.get("pages") or 1),
        "fields": fields,
    }
    result.update(suggest_routing_for_text(db, combined, fields))
    return result


def analyze_text(db: Session, text: str) -> Dict[str, Any]:
    """Field extraction and routing suggestion for text only (e.g. an e-mail
    body).  Nothing is stored."""
    fields = ocr_adapter.extract_text_fields(text) if _ocr_engine_ready() else {}
    fields = _json_safe(fields or {})
    result = {"success": True, "engine": "OCR_new", "fields": fields}
    result.update(suggest_routing_for_text(db, text, fields))
    return result


def warm_up_ocr_engine() -> None:
    """Load OCR models in the background at startup (best effort)."""
    if _ocr_engine_ready():
        try:
            ocr_adapter.warm_up()
        except Exception as e:
            print(f"[OCR] warm-up failed: {e}", flush=True)


def get_document(db: Session, doc_id: int) -> Optional[models.Document]:
    return db.query(models.Document).filter(models.Document.doc_id == doc_id).first()


def get_departments(db: Session) -> List[models.Department]:
    return db.query(models.Department).filter(models.Department.is_active.is_(True)).all()


def get_employees(db: Session) -> List[models.Employee]:
    return db.query(models.Employee).filter(models.Employee.is_active.is_(True)).all()


def get_document_ocr(db: Session, doc_id: int) -> Optional[models.DocumentOCR]:
    return db.query(models.DocumentOCR).filter(models.DocumentOCR.document_id == doc_id).first()


def get_routing_suggestion(db: Session, doc_id: int) -> Optional[models.RoutingSuggestion]:
    return db.query(models.RoutingSuggestion).filter(
        models.RoutingSuggestion.document_id == doc_id
    ).first()


def verify_extracted_field(
    db: Session, doc_id: int, field_name: str, verified_value: str, user: models.User
) -> Optional[models.DocumentExtractedField]:
    """The DS corrects an extracted value.  The original stays for provenance;
    `verified_value` is what the rest of the system trusts."""
    from sqlalchemy import func

    field_name = (field_name or "").strip()
    field = db.query(models.DocumentExtractedField).filter(
        models.DocumentExtractedField.document_id == doc_id,
        func.upper(models.DocumentExtractedField.field_name) == field_name.upper(),
    ).first()
    if not field:
        field = models.DocumentExtractedField(
            document_id=doc_id,
            field_name=field_name.upper(),  # stored field names are upper case
            extracted_value=None,
            confidence=None,
        )
        db.add(field)
    field.verified_value = verified_value
    field.verified_by = user.id
    field.verified_at = datetime.now()
    db.commit()
    db.refresh(field)
    return field


def generate_routing_suggestion(
    db: Session,
    doc_id: int,
    include_director_remark: bool = True,
    preferred_dept_id: Optional[int] = None,
    preferred_emp_id: Optional[int] = None
) -> Optional[models.RoutingSuggestion]:
    doc = get_document(db, doc_id)
    if not doc:
        return None

    depts = get_departments(db)
    suggested_dept_id: Optional[int] = preferred_dept_id or None
    suggested_emp_id: Optional[int] = preferred_emp_id

    ocr_record = db.query(models.DocumentOCR).filter(
        models.DocumentOCR.document_id == doc_id
    ).first()
    
    ocr_conf = ocr_record.confidence if (ocr_record and ocr_record.confidence and ocr_record.confidence > 0) else None
    confidence = ocr_conf if ocr_conf is not None else 0.0
    if suggested_dept_id or suggested_emp_id:
        # The DS picked the department/staff member on the intake form.
        confidence = 1.0
    reason = "Selected by the DS during document intake." if (suggested_dept_id or suggested_emp_id) else "Insufficient content to determine department."
    source = RoutingSource.DOCUMENT_CONTENT if (suggested_dept_id or suggested_emp_id) else RoutingSource.SOURCE_METADATA
    is_director_instruction = False
    
    # Check Director Remark
    if include_director_remark and doc.latest_director_remark:
        remark_lower = doc.latest_director_remark.lower()
        remark_tokens = _tokens(doc.latest_director_remark)
        employees = get_employees(db)
        for emp in employees:
            if emp.full_name and len(emp.full_name.strip()) > 3 and emp.full_name.lower() in remark_lower:
                suggested_emp_id = emp.user_id
                suggested_dept_id = emp.department_id
                confidence = 0.95
                dept_name = emp.department.name if emp.department else "unknown"
                reason = f"Director remark explicitly names {emp.full_name} ({dept_name}) for assignment."
                source = RoutingSource.DIRECTOR_REMARK
                is_director_instruction = True
                break

        if not is_director_instruction:
            for dept in depts:
                # Whole words only: a code such as "CR" must not match "director".
                code = (dept.code or "").strip()
                code_hit = bool(code) and re.search(
                    rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])",
                    doc.latest_director_remark,
                    0 if len(code) < 3 else re.IGNORECASE,
                ) is not None
                if _phrase_in(_tokens(dept.name), remark_tokens) or code_hit:
                    suggested_dept_id = dept.id
                    confidence = 0.92
                    reason = f"Director remark explicitly references {dept.name} department."
                    source = RoutingSource.DIRECTOR_REMARK
                    is_director_instruction = True
                    break

    ranked_depts_json = []
    confident_top = False
    is_ocr_ok = bool(
        ocr_record
        and ocr_record.ocr_status == OCRStatus.COMPLETED
        and ocr_record.extracted_text
        and ocr_record.extracted_text.strip()
    )

    # Ranking of every department against the stored OCR text (keywords +
    # semantic similarity).  Always computed when text exists so the DS can
    # see the full ranking; it only drives the suggestion when nothing more
    # explicit applies.
    if is_ocr_ok and depts:
        stored_fields = {
            f.field_name: f.effective_value
            for f in db.query(models.DocumentExtractedField).filter(
                models.DocumentExtractedField.document_id == doc_id
            ).all()
            if f.effective_value
        }
        try:
            ranking_text = "\n".join(t for t in (doc.title, doc.subject, ocr_record.extracted_text) if t)
            full_ranking = rank_departments(db, ranking_text, stored_fields, depts)
            ranked_depts_json = [
                {"department": r["department"], "department_id": r["department_id"], "score": r["score"]}
                for r in full_ranking
            ]
            confident_top = bool(full_ranking) and _is_confident_match(full_ranking[0])
        except Exception as e:
            ranked_depts_json = []
            print(f"Department ranking failed: {e}")

    if not suggested_dept_id and not suggested_emp_id:
        if is_ocr_ok:
            text_to_score = ocr_record.extracted_text
            text_lower = text_to_score.lower()

            if ranked_depts_json and confident_top:
                best_sim = ranked_depts_json[0]
                best_dept = next((d for d in depts if d.id == best_sim["department_id"]), None)
                if best_dept:
                    suggested_dept_id = best_dept.id
                    confidence = max(0.0, float(best_sim["score"]))
                    reason = f"Document content matches {best_dept.name} (score {confidence:.2f})."
                    source = RoutingSource.DOCUMENT_CONTENT

            # Employee extraction fallback
            emp = find_mentioned_employee(db, text_to_score)
            if emp is not None and emp.user_id:
                suggested_emp_id = emp.user_id
                reason += f" Staff '{emp.full_name}' explicitly mentioned in document text."

    if not suggested_dept_id and not suggested_emp_id:
        suggested_dept_id = None
        confidence = 0.0
        reason = "OCR extraction did not yield a departmental keyword match. Manual review required."
        source = RoutingSource.SOURCE_METADATA

    suggestion = db.query(models.RoutingSuggestion).filter(
        models.RoutingSuggestion.document_id == doc_id
    ).first()

    if not suggestion:
        suggestion = models.RoutingSuggestion(
            document_id=doc_id,
            suggested_department_id=suggested_dept_id,
            suggested_employee_id=suggested_emp_id,
            routing_confidence=confidence,
            routing_reason=reason,
            routing_source=source,
            is_director_instruction=is_director_instruction,
            ranked_departments=ranked_depts_json,
            generated_at=datetime.now(),
        )
        db.add(suggestion)
    elif not suggestion.confirmed_at:
        suggestion.suggested_department_id = suggested_dept_id
        suggestion.suggested_employee_id = suggested_emp_id
        suggestion.routing_confidence = confidence
        suggestion.routing_reason = reason
        suggestion.routing_source = source
        suggestion.is_director_instruction = is_director_instruction
        suggestion.ranked_departments = ranked_depts_json
        suggestion.generated_at = datetime.now()

    db.commit()
    db.refresh(suggestion)
    return suggestion


# File types OCR_new can read.
_OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".docx", ".txt"}


def _find_ocr_file(doc: models.Document) -> str:
    """Locate the stored file to OCR: the original document first, then any
    other attachment OCR_new can read."""
    _proj = Path(__file__).resolve().parent.parent
    _upl = Path(os.getenv("UPLOAD_DIR", str(_proj / "uploads")))
    bases = (_upl, Path(__file__).parent / "uploads", _proj / "uploads", Path("uploads"))

    attachments = sorted(
        doc.attachments or [],
        key=lambda a: (a.attachment_type != AttachmentType.ORIGINAL, a.id or 0),
    )
    for att in attachments:
        suffixes = {Path(att.storage_key or "").suffix.lower(), Path(att.file_name or "").suffix.lower()}
        if not suffixes & _OCR_EXTENSIONS:
            continue
        for base in bases:
            cand = Path(base) / att.storage_key
            if cand.exists():
                return str(cand)
    return ""


def _is_failed_intake_text(text: str) -> bool:
    """Error text from a failed desktop OCR run is not document content."""
    return text.lstrip().startswith("[OCR error")


def trigger_ocr_processing(
    db: Session,
    doc_id: int,
    intake_ocr_text: Optional[str] = None,
    intake_ocr_confidence: Optional[float] = None,
    preferred_dept_id: Optional[int] = None,
    preferred_emp_id: Optional[int] = None,
    intake_fields: Optional[Dict[str, Any]] = None,
) -> Optional[models.DocumentOCR]:
    """Run (or record) OCR for a document and refresh its routing suggestion.

    OCR is advisory: a failure is recorded on the OCR record and never stops
    the document from being registered.

    intake_ocr_text / intake_fields: text and fields the desktop intake
    already extracted with OCR_new, so the file is not OCR'd twice.
    """
    doc = get_document(db, doc_id)
    if not doc:
        return None

    ocr_record = db.query(models.DocumentOCR).filter(
        models.DocumentOCR.document_id == doc_id
    ).first()

    if not ocr_record:
        ocr_record = models.DocumentOCR(
            document_id=doc_id,
            ocr_status=OCRStatus.PENDING,
            processed_at=datetime.now()
        )
        db.add(ocr_record)

    ocr_record.ocr_status = OCRStatus.PENDING
    ocr_record.error_message = None
    doc.ocr_status = OCRStatus.PENDING

    # 1. Clear previous unverified extractions.  Values the DS verified are
    #    kept; they are what the rest of the system trusts.
    db.query(models.DocumentExtractedField).filter(
        models.DocumentExtractedField.document_id == doc_id,
        models.DocumentExtractedField.verified_value.is_(None),
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(ocr_record)

    intake_text = (intake_ocr_text or "").strip()
    if intake_text and _is_failed_intake_text(intake_text):
        intake_text = ""

    try:
        if intake_text:
            # The desktop intake already ran OCR_new on the file.
            ocr_record.extracted_text = intake_ocr_text
            ocr_record.confidence = intake_ocr_confidence
            ocr_record.ocr_status = OCRStatus.COMPLETED
            ocr_record.ocr_engine = "INTAKE_WEB_API"
            fields = intake_fields
            if not fields and _ocr_engine_ready():
                fields = ocr_adapter.extract_text_fields(intake_text)
            _store_extracted_fields(db, doc_id, fields)
        else:
            file_path = _find_ocr_file(doc)
            if _OCR_AVAILABLE and ocr_adapter is not None and file_path:
                res = ocr_adapter.process(file_path)
                if res.get("success"):
                    ocr_record.extracted_text = res.get("text")
                    ocr_record.confidence = res.get("confidence")
                    ocr_record.ocr_engine = res.get("engine") or "OCR_new"
                    ocr_record.ocr_status = OCRStatus.COMPLETED
                    _store_extracted_fields(db, doc_id, res.get("extracted_fields", {}))
                else:
                    ocr_record.ocr_status = OCRStatus.FAILED
                    ocr_record.error_message = res.get("error") or "OCR failed."
                    ocr_record.ocr_engine = "OCR_new"
            else:
                # Nothing to OCR: fall back to the document's own metadata.
                ocr_record.extracted_text = doc.title
                ocr_record.confidence = 0.5
                ocr_record.ocr_status = OCRStatus.COMPLETED
                ocr_record.ocr_engine = "FALLBACK_METADATA"
    except Exception as exc:
        db.rollback()
        db.refresh(ocr_record)
        ocr_record.ocr_status = OCRStatus.FAILED
        ocr_record.error_message = f"OCR processing error: {exc}"
        print(f"[OCR] document {doc_id}: {exc}", flush=True)

    ocr_record.processed_at = datetime.now()
    doc = get_document(db, doc_id)
    doc.ocr_status = ocr_record.ocr_status
    db.commit()
    db.refresh(ocr_record)

    try:
        generate_routing_suggestion(
            db,
            doc_id,
            include_director_remark=True,
            preferred_dept_id=preferred_dept_id,
            preferred_emp_id=preferred_emp_id
        )
    except Exception as exc:
        db.rollback()
        print(f"[ROUTING] suggestion for document {doc_id} failed: {exc}", flush=True)

    return ocr_record


def reanalyze_document_ocr(db: Session, doc_id: int) -> Optional[models.DocumentOCR]:
    """Re-run extraction on demand from the DS screen."""
    return trigger_ocr_processing(db, doc_id)
