"""
api/app.py
-----------
Local FastAPI application for the OCR & Document Intelligence Engine.

Usage
-----
Start the local service::

    uvicorn api.app:app --host 127.0.0.1 --port 8000

Endpoints
---------
  POST /process       – full document intelligence pipeline
  POST /ocr           – OCR only
  POST /classify      – classify text
  POST /extract       – extract entities from text
  GET  /health        – offline readiness check

The API binds to localhost only (127.0.0.1) and does NOT require
internet access during operation.

IMPORTANT: This module is optional.  The core engine works without it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    raise ImportError(
        "FastAPI and uvicorn are required to run the local API.\n"
        "Install with:  pip install fastapi uvicorn"
    )

from api.schemas import (
    ProcessRequest,
    ProcessResponse,
    OCRRequest,
    ClassifyRequest,
    ExtractRequest,
    HealthResponse,
)
from utils.logger import get_logger, setup_root_logger
from utils.offline_checker import OfflineChecker

setup_root_logger()
log = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Offline OCR & Document Intelligence Engine",
    description=(
        "A 100% offline document intelligence service. "
        "All inference runs locally — no internet required."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow only localhost origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Load application config once
# ──────────────────────────────────────────────────────────────────────────────

def _load_config() -> dict[str, Any]:
    try:
        import yaml
        config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        log.warning("Could not load config.yaml: %s", exc)
        return {}


_CONFIG: dict[str, Any] = _load_config()


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    """Check offline readiness and model availability."""
    checker = OfflineChecker(_CONFIG)
    check_result = checker.check()
    models_available = {
        k: v for k, v in check_result.items()
        if isinstance(v, bool)
    }
    all_ok = all(models_available.values()) if models_available else True
    return HealthResponse(
        status="READY" if all_ok else "DEGRADED",
        offline_mode=True,
        models_available=models_available,
    )


@app.post("/ocr", tags=["ocr"])
def run_ocr(request: OCRRequest) -> dict[str, Any]:
    """Run OCR-only pipeline on a document file."""
    t0 = time.perf_counter()
    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    try:
        from ocr.paddle_engine import PaddleOCREngine
        from ocr.ocr_pipeline import OCRPipeline

        engine = PaddleOCREngine()
        engine.initialize(_CONFIG)
        pipeline = OCRPipeline(engine=engine, config=_CONFIG)
        result = pipeline.process(file_path)
        result["api_elapsed_s"] = round(time.perf_counter() - t0, 3)
        return result

    except Exception as exc:
        log.error("OCR endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/classify", tags=["classification"])
def classify_text(request: ClassifyRequest) -> dict[str, Any]:
    """Classify document text using the configured classifier."""
    from classification.rule_classifier import RuleClassifier

    try:
        clf = RuleClassifier(config=_CONFIG)
        result = clf.classify(request.text)
        return result
    except Exception as exc:
        log.error("Classify endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/extract", tags=["extraction"])
def extract_entities(request: ExtractRequest) -> dict[str, Any]:
    """Extract named entities and structured fields from text."""
    from extraction.entity_extractor import EntityExtractor

    try:
        extractor = EntityExtractor(config=_CONFIG)
        result = extractor.extract(request.text)
        return result
    except Exception as exc:
        log.error("Extract endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/process", tags=["pipeline"])
def process_document(request: ProcessRequest) -> dict[str, Any]:
    """
    Run the full document intelligence pipeline.

    This is the primary endpoint — it chains OCR, layout analysis,
    text-type detection, NER, classification, and extraction.
    """
    t0 = time.perf_counter()
    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    cfg = dict(_CONFIG)
    if request.config_overrides:
        cfg.update(request.config_overrides)

    try:
        # OCR
        from ocr.paddle_engine import PaddleOCREngine
        from ocr.ocr_pipeline import OCRPipeline

        engine = PaddleOCREngine()
        engine.initialize(cfg)
        pipeline = OCRPipeline(engine=engine, config=cfg)
        ocr_result = pipeline.process(file_path)
        full_text = ocr_result.get("full_text", "")

        result: dict[str, Any] = {
            "document": {
                "filename":    file_path.name,
                "pages":       ocr_result.get("pages", 1),
                "source_type": ocr_result.get("doc_type", "UNKNOWN"),
            },
            "ocr": {
                "full_text": full_text,
                "regions":   ocr_result.get("regions", []),
            },
        }

        mode = request.mode.lower()

        # Classification
        if mode in ("classify", "full"):
            from classification.rule_classifier import RuleClassifier
            clf = RuleClassifier(config=cfg)
            result["classification"] = clf.classify(full_text)

        # NER + Extraction
        if mode in ("extract", "full"):
            from extraction.entity_extractor import EntityExtractor
            extractor = EntityExtractor(config=cfg)
            ext = extractor.extract(full_text)
            result["entities"] = ext.get("entities", [])
            result["extracted_fields"] = ext.get("extracted_fields", {})

        # Semantic
        if mode in ("understand", "full"):
            try:
                from semantic.semantic_pipeline import SemanticPipeline
                sem = SemanticPipeline(config=cfg)
                result["semantic"] = sem.process(full_text)
            except Exception as exc:
                log.warning("Semantic processing skipped: %s", exc)
                result["semantic"] = {"enabled": False, "error": str(exc)}

        result["metadata"] = {
            "mode":       mode,
            "elapsed_s":  round(time.perf_counter() - t0, 3),
        }
        return result

    except Exception as exc:
        log.error("Process endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
