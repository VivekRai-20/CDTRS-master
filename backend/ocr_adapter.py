import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

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


def _detect_director_instruction(regions: List[Dict[str, Any]]) -> Optional[str]:
    """Return the handwritten text that looks like a Director routing
    instruction, or None.  Uses Layout & Text Type (Handwriting) results."""
    for region in regions or []:
        # We also check if text_type was identified as HANDWRITTEN
        if region.get("text_type") == "HANDWRITTEN":
            text = region.get("text", "").lower()

            if "director" in text and "to director" in text:
                continue  # Addressed to director

            instruction_verbs = ["send to", "forward to", "discuss", "approved", "speak", "hod", "fctd"]
            if any(v in text for v in instruction_verbs) or "director" in text:
                return region.get("text", "")
    return None


class CDTRSOCRAdapter:
    def __init__(self):
        self.processor = DocumentProcessor() if _OCR_AVAILABLE else None

    def process(self, file_path: str, reference_texts: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Process the document and return a simplified dict.
        reference_texts: Used for semantic department matching.
        """
        if not self.processor:
            return {"error": "OCR system not available", "success": False}

        try:
            res = self.processor.process(file_path, mode="full", reference_texts=reference_texts)

            # Extract standard fields
            extracted = res.extracted_fields

            # Enhance with entities (like PERSON, DEPARTMENT)
            for ent in res.entities:
                label = ent.get("label", "")
                text = ent.get("text", "")
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
            }
        except SystemExit:
            logger.error(_MODELS_MISSING_MSG)
            return {"error": _MODELS_MISSING_MSG, "success": False}
        except Exception as e:
            logger.exception("OCR processing failed")
            return {"error": str(e), "success": False}

    def extract_text_fields(self, text: str) -> Dict[str, Any]:
        """Run OCR_new's entity + regex extraction on text that has already
        been read (no PaddleOCR needed).  Mirrors the extraction step of
        DocumentProcessor.process(): NER fields first, then regex fields."""
        if not self.processor or not text or not text.strip():
            return {}
        fields: Dict[str, Any] = {}
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

    def rank_references(self, text: str, reference_texts: List[str]) -> List[Dict[str, Any]]:
        """Semantic similarity of *text* to each reference text, best first.

        Works on text that has already been extracted, so the document is not
        OCR'd a second time.  Each item: {"reference": <original text>,
        "similarity": float}.
        """
        if not self.processor or not text or not text.strip() or not reference_texts:
            return []
        try:
            semantic = self.processor._get_semantic_pipeline().process(
                text, reference_texts=reference_texts
            )
        except (Exception, SystemExit) as e:
            logger.warning("Semantic ranking failed: %s", e)
            return []

        ranked: List[Dict[str, Any]] = []
        unmatched = list(reference_texts)
        for sim in (semantic or {}).get("similarities", []) or []:
            # OCR_new truncates each reference to 80 chars + "…" in its output;
            # map it back to the full reference text by prefix.
            shown = str(sim.get("reference", ""))
            prefix = shown[:-1] if shown.endswith("…") else shown
            if not prefix:
                continue
            match =next((r for r in unmatched if r == shown or r.startswith(prefix)), None)
            if match is None:
                continue
            unmatched.remove(match)
            try:
                score = float(sim.get("similarity", 0.0))
            except (TypeError, ValueError):
                continue
            ranked.append({"reference": match, "similarity": score})

        ranked.sort(key=lambda item: item["similarity"], reverse=True)
        return ranked


ocr_adapter = CDTRSOCRAdapter()
