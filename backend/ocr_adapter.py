import sys
import re
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Sequence

# Fix Windows DLL conflict between PyTorch and PaddlePaddle by loading torch first
try:
    import torch
except Exception:  # ImportError, or OSError when a torch DLL fails to load
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OCR_DIR = _PROJECT_ROOT / "OCR_new"
if str(_OCR_DIR) not in sys.path:
    sys.path.insert(0, str(_OCR_DIR))

try:
    # Explicitly import layout modules to ensure they are cached and paths are resolved
    import layout.layout_analyzer
except Exception as e:
    print('Failed to pre-load layout:', e)

try:
    from document_intelligence import DocumentProcessor
    _OCR_AVAILABLE = True
except Exception as e:
    _OCR_AVAILABLE = False
    DocumentProcessor = None
    print('OCR unavailable:', e)

logger = logging.getLogger(__name__)

ENGINE_NAME = "OCR_new"

# OCR_new calls sys.exit() when its offline PaddleOCR models are missing.
_MODELS_MISSING_MSG = (
    "OCR_new stopped: PaddleOCR models were not found. "
    "Run 'python OCR_new/setup_models.py' once to install them."
)


def _average_confidence(regions: List[Dict[str, Any]]) -> float:
    """Mean recognition confidence over all OCR regions (0.0 when none)."""
    scores = [
        float(r["confidence"])
        for r in regions or []
        if isinstance(r.get("confidence"), (int, float))
    ]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _is_mostly_handwritten(regions: List[Dict[str, Any]]) -> bool:
    types = [r.get("text_type") for r in regions or []]
    return types.count("HANDWRITTEN") > types.count("PRINTED")


# ---------------------------------------------------------------------------
# Director instruction detection
# ---------------------------------------------------------------------------

# Lines that address the Director or open/close a letter are not instructions,
# even when the text-type detector marks them as handwritten.
_ADDRESS_LINE = re.compile(
    r"^\s*(?:to\b|the\s+director\b|director\s*,|dear\b|respected\b|sir\b|madam\b|"
    r"subject\b|sub\s*[:.\-]|ref(?:erence)?\b|dated?\b|from\b|yours\b|through\b|copy\s+to\b)",
    re.IGNORECASE,
)
_INSTRUCTION_TERMS = re.compile(
    r"\b(?:forward(?:ed)?|fwd|send|sent|put\s+up|pl(?:s|ease)?|discuss(?:ed)?|approved?|"
    r"agreed?|noted|necessary\s+action|n\s*/\s*a|for\s+action|action|examine|comments?|"
    r"may\s+be|do\s+the\s+needful|see\s+me|speak|call|process|urgent(?:ly)?|expedite|asap|"
    r"hod|fctd|reply|issue|draft|check|verify|immediately|priority)\b",
    re.IGNORECASE,
)
_DIRECTOR_WORD = re.compile(r"\b(?:director|dir\.?)\b", re.IGNORECASE)


def _bbox(region: Dict[str, Any]) -> List[float]:
    b = region.get("bbox") or [0, 0, 0, 0]
    return [float(v) for v in b] if len(b) == 4 else [0.0, 0.0, 0.0, 0.0]


def _handwritten_lines(regions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group handwritten regions into text lines (page, top-to-bottom)."""
    hw = [r for r in regions or [] if r.get("text_type") == "HANDWRITTEN" and str(r.get("text", "")).strip()]
    hw.sort(key=lambda r: (r.get("page", 1), (_bbox(r)[1] + _bbox(r)[3]) / 2.0, _bbox(r)[0]))
    lines: List[Dict[str, Any]] = []
    for r in hw:
        x1, y1, x2, y2 = _bbox(r)
        height = max(1.0, y2 - y1)
        mid = (y1 + y2) / 2.0
        line = lines[-1] if lines else None
        if (
            line is not None
            and line["page"] == r.get("page", 1)
            and abs(mid - line["mid"]) <= max(12.0, 0.6 * max(height, line["height"]))
        ):
            line["regions"].append(r)
            line["top"] = min(line["top"], y1)
            line["bottom"] = max(line["bottom"], y2)
            line["height"] = max(line["height"], height)
        else:
            lines.append({
                "page": r.get("page", 1), "mid": mid, "top": y1, "bottom": y2,
                "height": height, "regions": [r],
            })
    for line in lines:
        line["regions"].sort(key=lambda r: _bbox(r)[0])
        line["text"] = " ".join(str(r.get("text", "")).strip() for r in line["regions"]).strip()
        confs = [float(r.get("confidence", 1.0)) for r in line["regions"]]
        line["confidence"] = sum(confs) / len(confs) if confs else 1.0
    return lines


def _instruction_score(line: Dict[str, Any]) -> float:
    text = line["text"]
    if len(re.sub(r"[^A-Za-z0-9]", "", text)) < 3:
        return -1.0
    if _ADDRESS_LINE.search(text):
        return -5.0
    score = 2.0 * len(_INSTRUCTION_TERMS.findall(text))
    if _DIRECTOR_WORD.search(text):
        score += 1.0
    # A line counts only with an instruction word or "Director" in it, so
    # ordinary handwritten pages (notes, handwritten letters) are not taken
    # for a Director's remark.  Among candidates, a less confidently read
    # line (typical of hurried handwriting) is preferred.
    if score > 0 and line.get("confidence", 1.0) < 0.9:
        score += 0.5
    return score


def _detect_director_instruction(regions: List[Dict[str, Any]]) -> Optional[str]:
    """Return the handwritten Director instruction on the page, or None.

    Handwritten regions are grouped into lines; lines that address the
    Director ("To, The Director ...") or open/close the letter are ignored.
    The best instruction line is returned together with the handwritten lines
    directly above/below it, so a note written over two or three lines is
    returned whole instead of a single fragment.
    """
    lines = _handwritten_lines(regions)
    if not lines:
        return None
    scored = [(i, _instruction_score(line)) for i, line in enumerate(lines)]
    best_i, best_score = max(scored, key=lambda item: item[1])
    if best_score <= 0:
        return None

    def close(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        gap = b["top"] - a["bottom"]
        return a["page"] == b["page"] and gap <= 1.8 * max(a["height"], b["height"])

    picked = [best_i]
    i = best_i
    while i + 1 < len(lines) and len(picked) < 4 and close(lines[i], lines[i + 1]) and _instruction_score(lines[i + 1]) >= 0:
        i += 1
        picked.append(i)
    i = best_i
    while i - 1 >= 0 and len(picked) < 4 and close(lines[i - 1], lines[i]) and _instruction_score(lines[i - 1]) >= 0:
        i -= 1
        picked.insert(0, i)
    return " ".join(lines[j]["text"] for j in picked).strip() or None


class CDTRSOCRAdapter:
    """The backend's single entry point to OCR_new.

    One DocumentProcessor is shared by every request; PaddleOCR and the
    embedding / NER models are not safe to run from several threads at once,
    so every call into the engine is serialised with a lock.
    """

    def __init__(self):
        self.processor = DocumentProcessor() if _OCR_AVAILABLE else None
        self._lock = threading.RLock()
        self._embedding_engine = None
        self._embedding_failed = False
        self._reference_cache: Dict[tuple, Any] = {}

    # ------------------------------------------------------------------
    # Warm-up
    # ------------------------------------------------------------------

    def warm_up(self) -> None:
        """Load the OCR, NER and embedding models ahead of the first request,
        so the first upload does not wait for model loading."""
        if not self.processor:
            return
        with self._lock:
            try:
                self.processor._get_ocr_pipeline()
            except (Exception, SystemExit) as e:
                logger.warning("OCR warm-up skipped: %s", e)
            try:
                self.processor._get_entity_extractor()
                self.processor._get_regex_engine()
            except Exception as e:
                logger.warning("Extraction warm-up skipped: %s", e)
            try:
                engine = self._get_embedding_engine()
                if engine is not None:
                    engine.encode("warm up")
            except Exception as e:
                logger.warning("Embedding warm-up skipped: %s", e)

    # ------------------------------------------------------------------
    # OCR a file
    # ------------------------------------------------------------------

    def process(self, file_path: str, reference_texts: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Process the document and return a simplified dict.
        reference_texts: Used for semantic department matching.
        """
        if not self.processor:
            return {"error": "OCR system not available", "success": False}

        try:
            with self._lock:
                res = self.processor.process(file_path, mode="full", reference_texts=reference_texts)

            # Extract standard fields
            extracted = res.extracted_fields

            # Enhance with entities (like PERSON, DEPARTMENT) that the entity
            # extractor did not already turn into a field (persons,
            # organizations, dates, ...).
            try:
                from extraction.entity_extractor import _LABEL_TO_FIELD
            except Exception:
                _LABEL_TO_FIELD = {}
            for ent in res.entities:
                label = ent.get("label", "")
                text = ent.get("text", "")
                if _LABEL_TO_FIELD.get(label.upper()) in extracted:
                    continue
                if label and text:
                    # Collect all mentions of people or departments
                    key = label.lower()
                    if key not in extracted:
                        extracted[key] = []
                    if isinstance(extracted[key], list):
                        extracted[key].append(text)
                    else:
                        extracted[key] = [extracted[key], text]

            # Detect Director instructions written by hand on the document
            director_remark = _detect_director_instruction(res.regions)
            if director_remark is not None:
                extracted["prior_director_review_detected"] = "true"
                extracted["director_handwritten_remark"] = director_remark

            return {
                "success": True,
                "text": res.full_text,
                "confidence": _average_confidence(res.regions),
                "extracted_fields": extracted,
                "similarities": res.semantic.get("similarities", []) if res.semantic else [],
                "engine": ENGINE_NAME,
                "pages": int(res.pages or 1),
                "is_handwritten": _is_mostly_handwritten(res.regions),
                "source_type": res.source_type,
            }
        except SystemExit:
            logger.error(_MODELS_MISSING_MSG)
            return {"error": _MODELS_MISSING_MSG, "success": False}
        except Exception as e:
            logger.exception("OCR processing failed")
            return {"error": str(e), "success": False}

    # ------------------------------------------------------------------
    # Text-only extraction
    # ------------------------------------------------------------------

    def extract_text_fields(self, text: str) -> Dict[str, Any]:
        """Run OCR_new's entity + regex extraction on text that has already
        been read (no PaddleOCR needed).  Mirrors the extraction step of
        DocumentProcessor.process(): NER fields first, then regex fields."""
        if not self.processor or not text or not text.strip():
            return {}
        fields: Dict[str, Any] = {}
        with self._lock:
            try:
                ext_out = self.processor._get_entity_extractor().extract(text)
                fields.update(ext_out.get("extracted_fields", {}))
            except Exception as e:
                logger.warning("OCR_new entity extraction failed: %s", e)
            try:
                for field_name, res in self.processor._get_regex_engine().extract(text).items():
                    val = res.value if hasattr(res, "value") else res
                    if val is not None and field_name not in fields:
                        fields[field_name] = val
            except Exception as e:
                logger.warning("OCR_new regex extraction failed: %s", e)
        return fields

    # ------------------------------------------------------------------
    # Semantic similarity
    # ------------------------------------------------------------------

    def _get_embedding_engine(self):
        """OCR_new's local sentence-embedding model (loaded once)."""
        if self._embedding_engine is not None or self._embedding_failed or not self.processor:
            return self._embedding_engine
        try:
            from semantic.embedding_engine import EmbeddingEngine
            engine = EmbeddingEngine(config=self.processor.config)
            engine.initialize()
            self._embedding_engine = engine
        except Exception as e:
            self._embedding_failed = True
            logger.warning("Embedding model unavailable, using keyword matching only: %s", e)
        return self._embedding_engine

    def rank_references(self, text: str, reference_texts: List[str]) -> List[Dict[str, Any]]:
        """Semantic similarity of *text* to each reference text, best first.

        Works on text that has already been extracted, so the document is not
        OCR'd a second time.  Each item: {"reference": <original text>,
        "similarity": float in [-1, 1]}.
        """
        if not self.processor or not text or not text.strip() or not reference_texts:
            return []
        try:
            import numpy as np
            with self._lock:
                engine = self._get_embedding_engine()
                if engine is None:
                    return []
                key = tuple(reference_texts)
                ref_vectors = self._reference_cache.get(key)
                if ref_vectors is None:
                    ref_vectors = np.asarray(engine.encode([r[:4096] for r in reference_texts]))
                    if len(self._reference_cache) > 16:
                        self._reference_cache.clear()
                    self._reference_cache[key] = ref_vectors
                doc_vector = np.asarray(engine.encode(text[:4096]))
            ref_norms = np.linalg.norm(ref_vectors, axis=1)
            doc_norm = float(np.linalg.norm(doc_vector))
            if doc_norm == 0.0:
                return []
            sims = (ref_vectors @ doc_vector) / np.where(ref_norms == 0, 1.0, ref_norms) / doc_norm
        except (Exception, SystemExit) as e:
            logger.warning("Semantic ranking failed: %s", e)
            return []

        ranked = [
            {"reference": ref, "similarity": float(sim)}
            for ref, sim in zip(reference_texts, sims.tolist())
        ]
        ranked.sort(key=lambda item: item["similarity"], reverse=True)
        return ranked


ocr_adapter = CDTRSOCRAdapter()
