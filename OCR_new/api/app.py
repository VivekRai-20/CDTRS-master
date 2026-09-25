"""
api/app.py
-----------
Local FastAPI application for the OCR & Document Intelligence Engine.

Usage
-----
Start the local service from the OCR_new folder (use a port the CDTRS
backend is not using)::

    python -m uvicorn api.app:app --host 127.0.0.1 --port 8010

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

import threading
import time
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    raise ImportError(
        "FastAPI and uvicorn are required to run the local API "
        "(both are pinned in requirements.txt)."
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
from utils.offline_checker import check_model_dirs, check_patterns_file

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

_PROCESSOR = None
_PROCESS_LOCK = threading.Lock()  # one document at a time on the shared processor


def _processor(overrides: dict[str, Any] | None = None):
    """One DocumentProcessor for all requests (models load once); a separate
    one when a request overrides settings."""
    global _PROCESSOR
    from document_intelligence import DocumentProcessor

    if overrides:
        cfg = dict(_CONFIG)
        cfg.update(overrides)
        return DocumentProcessor(config=cfg)
    if _PROCESSOR is None:
        _PROCESSOR = DocumentProcessor(config=_CONFIG)
    return _PROCESSOR


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    """Check offline readiness and model availability."""
    paddle_ok, _missing = check_model_dirs(_CONFIG)
    models_available = {
        "paddleocr": paddle_ok,
        "patterns_file": check_patterns_file(_CONFIG),
    }
    all_ok = all(models_available.values())
    return HealthResponse(
        status="READY" if all_ok else "DEGRADED",
        offline_mode=True,
        models_available=models_available,
    )


@app.post("/ocr", tags=["ocr"])
def run_ocr(request: OCRRequest) -> dict[str, Any]:
    """OCR only (the language comes from config.yaml; the request field is ignored)."""
    t0 = time.perf_counter()
    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    try:
        with _PROCESS_LOCK:
            result = _processor().process(file_path, mode="ocr").to_dict()
        result.setdefault("metadata", {})["api_elapsed_s"] = round(time.perf_counter() - t0, 3)
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
    Run the document intelligence pipeline (the same DocumentProcessor the
    command line and CDTRS use).  mode: ocr | understand | classify | extract | full.
    """
    t0 = time.perf_counter()
    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    mode = request.mode.lower()
    if mode not in ("ocr", "understand", "classify", "extract", "full"):
        raise HTTPException(status_code=422, detail=f"Unknown mode '{request.mode}'.")
    try:
        with _PROCESS_LOCK:
            result = _processor(request.config_overrides).process(file_path, mode=mode).to_dict()
        result.setdefault("metadata", {})["api_elapsed_s"] = round(time.perf_counter() - t0, 3)
        return result
    except Exception as exc:
        log.error("Process endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
