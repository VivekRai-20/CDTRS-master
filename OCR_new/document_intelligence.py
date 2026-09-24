"""
document_intelligence.py
-------------------------
Reusable Document Intelligence Engine and Python SDK entry point.

As specified in Section 23 of README.md:

    from document_intelligence import DocumentProcessor

    processor = DocumentProcessor()
    result = processor.process("document.pdf")

    print(result.document_type)
    print(result.text)
    print(result.entities)
    print(result.extracted_fields)

All processing is 100% offline — local inference only, zero network access.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml

from utils.logger import get_logger, setup_root_logger
log = get_logger(__name__)
_ROOT = Path(__file__).resolve().parent

import sys
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ──────────────────────────────────────────────────────────────────────────────
# DocumentResult
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentResult:
    """
    Standardized result object returned by DocumentProcessor.process().
    Conforms to README Sections 20, 21, 23, and 39.
    """

    filename: str
    source_type: str
    pages: int
    full_text: str = ""
    regions: list[dict[str, Any]] = field(default_factory=list)
    layout: list[dict[str, Any]] = field(default_factory=list)
    text_types: list[dict[str, Any]] = field(default_factory=list)
    classification: dict[str, Any] = field(default_factory=dict)
    entities: list[dict[str, Any]] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    semantic: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Convenience properties matching README Section 23 ────────────────── #

    @property
    def document_type(self) -> str:
        """Alias for classification label or source format."""
        if self.classification and self.classification.get("label"):
            return self.classification["label"]
        return self.source_type

    @property
    def text(self) -> str:
        """Alias for full_text."""
        return self.full_text

    # ── Serialization matching Section 21 & Section 39 ────────────────────── #

    def to_dict(self) -> dict[str, Any]:
        """Convert result to the standardized JSON schema specified in README Section 21/39."""
        return {
            "document": {
                "filename": self.filename,
                "pages": self.pages,
                "source_type": self.source_type,
            },
            "classification": self.classification if self.classification else {
                "label": "UNKNOWN",
                "confidence": 0.0,
            },
            "regions": self.regions,
            "layout": {
                "regions": self.layout,
            } if self.layout else {},
            "text_types": self.text_types,
            "entities": self.entities,
            "extracted_fields": self.extracted_fields,
            "semantic": self.semantic,
            "full_text": self.full_text,
            "text": self.full_text,
            "ocr": {
                "text": self.full_text,
                "full_text": self.full_text,
                "regions": self.regions,
            },
            "metadata": self.metadata,
        }

    def save(self, output_dir: str | Path | None = None) -> dict[str, Path]:
        """
        Write all output files (ocr.txt, ocr.json, layout.json, text_types.json,
        entities.json, semantic.json, classification.json, extracted.json, result.json)
        to the output directory matching Section 38.
        """
        from output.json_writer import JSONWriter
        from output.text_writer import TextWriter

        out_root = Path(output_dir) if output_dir else _ROOT / "output"
        json_writer = JSONWriter(output_dir=out_root)
        text_writer = TextWriter(output_dir=out_root)

        d = self.to_dict()
        doc_stem = Path(self.filename).stem

        written: dict[str, Path] = {}
        written["result.json"] = json_writer.write(d, doc_stem)
        written["ocr.txt"] = text_writer.write(d, doc_stem)

        doc_dir = out_root / doc_stem
        for name in [
            "ocr.json",
            "layout.json",
            "text_types.json",
            "entities.json",
            "semantic.json",
            "classification.json",
            "extracted.json",
        ]:
            p = doc_dir / name
            if p.exists():
                written[name] = p

        return written


# ──────────────────────────────────────────────────────────────────────────────
# DocumentProcessor
# ──────────────────────────────────────────────────────────────────────────────

class DocumentProcessor:
    """
    High-level, reusable Document Intelligence Processor.
    100% offline, modular, model-agnostic.

    Parameters
    ----------
    config : dict, optional
        Pre-loaded configuration dictionary.
    config_path : str or Path, optional
        Path to config.yaml (defaults to config/config.yaml).
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        if config is not None:
            self.config = dict(config)
        else:
            cfg_path = Path(config_path) if config_path else _ROOT / "config" / "config.yaml"
            self.config = self._load_config(cfg_path)

        setup_root_logger(self.config.get("logging", {}))
        self._ocr_engine = None
        self._ocr_pipeline = None
        self._layout_analyzer = None
        self._text_type_detector = None
        self._rule_classifier = None
        self._entity_extractor = None
        self._regex_engine = None
        self._semantic_pipeline = None

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            log.warning("Config file not found: %s. Using empty config.", path)
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    # ── Lazy initializers ─────────────────────────────────────────────────── #

    def _get_ocr_pipeline(self):
        if self._ocr_pipeline is None:
            from utils.offline_checker import abort_if_models_missing
            from ocr.paddle_engine import PaddleEngine
            from ocr.ocr_pipeline import OCRPipeline

            abort_if_models_missing(self.config)
            self._ocr_engine = PaddleEngine()
            self._ocr_engine.initialize(self.config)
            self._ocr_pipeline = OCRPipeline(self._ocr_engine, self.config)
        return self._ocr_pipeline

    def _get_layout_analyzer(self):
        if self._layout_analyzer is None:
            from layout.layout_analyzer import LayoutAnalyzer
            self._layout_analyzer = LayoutAnalyzer(self.config)
        return self._layout_analyzer

    def _get_text_type_detector(self):
        if self._text_type_detector is None:
            from ocr.text_type_detector import TextTypeDetector
            self._text_type_detector = TextTypeDetector(self.config)
        return self._text_type_detector

    def _get_rule_classifier(self):
        if self._rule_classifier is None:
            from classification.rule_classifier import RuleClassifier
            self._rule_classifier = RuleClassifier(self.config)
        return self._rule_classifier

    def _get_entity_extractor(self):
        if self._entity_extractor is None:
            from extraction.entity_extractor import EntityExtractor
            self._entity_extractor = EntityExtractor(self.config)
        return self._entity_extractor

    def _get_regex_engine(self):
        if self._regex_engine is None:
            from extraction.pattern_manager import PatternManager
            from extraction.regex_engine import RegexEngine

            paths_cfg = self.config.get("paths", {})
            patterns_file = _ROOT / paths_cfg.get("patterns_file", "extraction/patterns.yaml")
            pm = PatternManager(patterns_file)
            pm.load()
            self._regex_engine = RegexEngine(pm)
        return self._regex_engine

    def _get_semantic_pipeline(self):
        if self._semantic_pipeline is None:
            from semantic.semantic_pipeline import SemanticPipeline
            self._semantic_pipeline = SemanticPipeline(self.config)
        return self._semantic_pipeline

    # ── Main processing method ────────────────────────────────────────────── #

    def process(
        self,
        file_path: str | Path,
        mode: str = "full",
        reference_texts: list[str] | None = None,
    ) -> DocumentResult:
        """
        Process a document using the offline intelligence engine.

        Parameters
        ----------
        file_path : str or Path
            Path to the document (PDF, PNG, JPG, TIFF, DOCX, TXT).
        mode : str
            Processing mode: "ocr", "understand", "classify", "extract", or "full".
        reference_texts : list[str], optional
            Reference texts for semantic similarity comparison.

        Returns
        -------
        DocumentResult
        """
        t0 = time.perf_counter()
        target_path = Path(file_path).resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"Input file not found: {target_path}")

        mode = mode.lower()
        log.info("DocumentProcessor.process: file=%s, mode=%s", target_path.name, mode)

        # ── Step 1: Normalization & Document Loading ──────────────────────── #
        from document.document_normalizer import normalize
        norm_doc = normalize(target_path, self.config)
        num_pages = max(1, norm_doc.page_count)
        source_type = norm_doc.source_format

        # ── Step 2: OCR Recognition ───────────────────────────────────────── #
        pipeline = self._get_ocr_pipeline()
        ocr_out = pipeline.process(target_path)
        regions = ocr_out.get("regions", [])
        full_text = ocr_out.get("full_text", "")
        pages_processed = ocr_out.get("pages", num_pages)

        # ── Step 3: Layout Analysis ───────────────────────────────────────── #
        layout_regions: list[dict[str, Any]] = []
        if mode in ("full",):
            try:
                analyzer = self._get_layout_analyzer()
                pages_tuples = [(p.page_number, p.image) for p in norm_doc.pages]
                if pages_tuples:
                    layout_regions = analyzer.analyze_document(pages_tuples)
            except Exception as exc:
                log.warning("Layout analysis skipped: %s", exc)

        # ── Step 4: Text-Type Detection ───────────────────────────────────── #
        text_types_summary: list[dict[str, Any]] = []
        if mode in ("full",):
            try:
                tt_detector = self._get_text_type_detector()
                # Run detection on each page's regions
                for p in norm_doc.pages:
                    page_regions = [r for r in regions if r.get("page", 1) == p.page_number]
                    if page_regions and p.image is not None:
                        tt_detector.detect_regions(page_regions, p.image)
                # Build summary
                for r in regions:
                    if "text_type" in r:
                        text_types_summary.append({
                            "page": r.get("page", 1),
                            "text": r.get("text", "")[:40],
                            "text_type": r.get("text_type", "UNKNOWN"),
                            "confidence": r.get("text_type_confidence", 0.0),
                        })
            except Exception as exc:
                log.warning("Text-type detection skipped: %s", exc)

        # ── Step 5: Document Classification ───────────────────────────────── #
        classification_result: dict[str, Any] = {}
        if mode in ("classify", "full"):
            try:
                classifier = self._get_rule_classifier()
                classification_result = classifier.classify(full_text)
            except Exception as exc:
                log.warning("Rule classification failed: %s", exc)
                classification_result = {"label": "UNKNOWN", "confidence": 0.0}

        # ── Step 6: Information & Entity Extraction ───────────────────────── #
        entities: list[dict[str, Any]] = []
        extracted_fields: dict[str, Any] = {}

        if mode in ("extract", "full"):
            try:
                # 1. NER entities
                extractor = self._get_entity_extractor()
                ext_out = extractor.extract(full_text)
                entities = ext_out.get("entities", [])
                extracted_fields.update(ext_out.get("extracted_fields", {}))
            except Exception as exc:
                log.warning("Entity extraction failed: %s", exc)

            try:
                # 2. Regex pattern extraction
                regex_eng = self._get_regex_engine()
                pattern_results = regex_eng.extract(full_text)
                for field_name, res in pattern_results.items():
                    val = res.value if hasattr(res, "value") else res
                    if val is not None and field_name not in extracted_fields:
                        extracted_fields[field_name] = val
            except Exception as exc:
                log.warning("Regex extraction failed: %s", exc)

        # ── Step 7: Semantic Understanding ────────────────────────────────── #
        semantic_result: dict[str, Any] = {}
        if mode in ("understand", "full"):
            try:
                sem_pipe = self._get_semantic_pipeline()
                semantic_result = sem_pipe.process(full_text, reference_texts=reference_texts)

                # If rule classification was unknown or not run, enrich from semantic classification
                sem_cls = semantic_result.get("classification", {})
                if sem_cls and sem_cls.get("label") and sem_cls.get("label") != "UNKNOWN":
                    if not classification_result or classification_result.get("label") == "UNKNOWN":
                        classification_result = sem_cls
            except Exception as exc:
                log.warning("Semantic pipeline skipped: %s", exc)
                semantic_result = {"enabled": False, "error": str(exc)}

        elapsed = round(time.perf_counter() - t0, 3)

        metadata = {
            "mode": mode,
            "elapsed_s": elapsed,
            "region_count": len(regions),
            "pages_processed": pages_processed,
        }

        return DocumentResult(
            filename=target_path.name,
            source_type=source_type,
            pages=pages_processed,
            full_text=full_text,
            regions=regions,
            layout=layout_regions,
            text_types=text_types_summary,
            classification=classification_result,
            entities=entities,
            extracted_fields=extracted_fields,
            semantic=semantic_result,
            metadata=metadata,
        )
