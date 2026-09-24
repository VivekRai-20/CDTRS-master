"""
api/schemas.py
---------------
Pydantic request and response schemas for the local OCR API.

These schemas define the contract between the local REST API and
any application consuming it.  No external schemas are imported.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError(
        "Pydantic is required for the local API.\n"
        "Install with:  pip install pydantic"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Request schemas
# ──────────────────────────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    """Request body for the /process endpoint."""
    file_path: str = Field(..., description="Absolute or relative path to the input document.")
    mode: str = Field(
        default="full",
        description="Processing mode: 'ocr' | 'understand' | 'classify' | 'extract' | 'full'.",
    )
    config_overrides: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional config key overrides for this request.",
    )


class OCRRequest(BaseModel):
    """Request body for the /ocr endpoint."""
    file_path: str
    language: Optional[str] = "en"


class ClassifyRequest(BaseModel):
    """Request body for the /classify endpoint."""
    text: str = Field(..., description="OCR text to classify.")


class ExtractRequest(BaseModel):
    """Request body for the /extract endpoint."""
    text: str = Field(..., description="OCR text to extract entities from.")


# ──────────────────────────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────────────────────────

class RegionResult(BaseModel):
    text: str
    confidence: float
    bbox: list[int]
    page: int
    text_type: Optional[str] = None
    region_type: Optional[str] = None
    reading_order: Optional[int] = None


class OCRResponse(BaseModel):
    file: str
    doc_type: str
    pages: int
    elapsed_s: float
    full_text: str
    regions: list[RegionResult]


class ClassificationResult(BaseModel):
    label: str
    confidence: float
    method: Optional[str] = None


class EntityResult(BaseModel):
    text: str
    label: str
    confidence: Optional[float] = None
    normalized_text: Optional[str] = None


class SemanticResult(BaseModel):
    enabled: bool
    keywords: Optional[list[dict[str, Any]]] = None
    classification: Optional[dict[str, Any]] = None
    similarities: Optional[list[dict[str, Any]]] = None


class ProcessResponse(BaseModel):
    """Full response from the /process endpoint."""
    document: dict[str, Any]
    ocr: Optional[dict[str, Any]] = None
    layout: Optional[list[dict[str, Any]]] = None
    classification: Optional[ClassificationResult] = None
    entities: Optional[list[EntityResult]] = None
    semantic: Optional[SemanticResult] = None
    extracted_fields: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""
    status: str
    offline_mode: bool
    models_available: dict[str, bool]
