"""
semantic/document_classifier.py
---------------------------------
Semantic similarity-based document classification.

How it works
------------
1.  A set of category definitions (label + description text) is loaded
    from config or a local YAML file.
2.  Each category description is embedded once and cached.
3.  A new document's text is embedded and compared (cosine similarity)
    to all category embeddings.
4.  The category with the highest similarity score is returned as the
    best match, along with a ranked list of all categories.

Category definitions example (config.yaml)
------------------------------------------
::

    classification:
      enabled: true
      method: semantic
      categories_file: "config/categories.yaml"

categories.yaml format::

    categories:
      - label: TECHNICAL_REPORT
        description: "A technical report describing engineering work, systems, or projects."
      - label: INVOICE
        description: "A commercial document requesting payment for goods or services."
      - label: LEAVE_APPLICATION
        description: "A formal request for leave or absence from work."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from semantic.embedding_engine import EmbeddingEngine
from semantic.semantic_similarity import rank_by_similarity
from utils.logger import get_logger

log = get_logger(__name__)

# Default built-in categories (used when no external file is configured)
_DEFAULT_CATEGORIES = [
    {
        "label": "TECHNICAL_REPORT",
        "description": "A technical report describing engineering systems, projects, or research findings.",
    },
    {
        "label": "INVOICE",
        "description": "A commercial document requesting payment for goods or services rendered, with amounts and vendor details.",
    },
    {
        "label": "LEAVE_APPLICATION",
        "description": "A formal written request for leave or absence from work or school.",
    },
    {
        "label": "LETTER",
        "description": "A formal or informal letter addressed to an individual or organisation.",
    },
    {
        "label": "FORM",
        "description": "A structured document with fields to be filled in, such as an application form or registration form.",
    },
    {
        "label": "CONTRACT",
        "description": "A legal agreement or contract between two or more parties.",
    },
    {
        "label": "RESUME",
        "description": "A curriculum vitae or resume listing personal details, education, and work experience.",
    },
    {
        "label": "GENERAL",
        "description": "A general document that does not fit any specific category.",
    },
]


class SemanticDocumentClassifier:
    """
    Classify a document by comparing its embedding to category embeddings.

    Parameters
    ----------
    embedding_engine : EmbeddingEngine
        An initialised embedding engine.
    config : dict
        Full application configuration.
    """

    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        config: dict | None = None,
    ) -> None:
        self._engine = embedding_engine
        self._config = config or {}
        self._category_embeddings: list[dict[str, Any]] = []
        self._categories_loaded = False

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def classify(self, text: str) -> dict[str, Any]:
        """
        Classify *text* against known document categories.

        Parameters
        ----------
        text : str
            Full OCR-extracted text of the document.

        Returns
        -------
        dict::

            {
                "label":      str,    # top category
                "confidence": float,  # similarity score of top category
                "categories": [       # all categories ranked
                    {"label": str, "similarity": float}, …
                ]
            }
        """
        if not text.strip():
            return {"label": "UNKNOWN", "confidence": 0.0, "categories": []}

        self._ensure_categories_loaded()

        doc_embedding = self._engine.encode(text[:2000])  # cap for speed
        ranked = rank_by_similarity(
            doc_embedding,
            self._category_embeddings,
            embedding_key="embedding",
            label_key="label",
        )

        if not ranked:
            return {"label": "UNKNOWN", "confidence": 0.0, "categories": []}

        top = ranked[0]
        return {
            "label":      top["label"],
            "confidence": top["similarity"],
            "categories": ranked,
        }

    # ------------------------------------------------------------------ #
    # Category loading                                                     #
    # ------------------------------------------------------------------ #

    def _ensure_categories_loaded(self) -> None:
        if self._categories_loaded:
            return

        categories = self._load_categories()
        log.info("Embedding %d document categories…", len(categories))

        for cat in categories:
            emb = self._engine.encode(cat["description"])
            self._category_embeddings.append(
                {"label": cat["label"], "embedding": emb}
            )

        self._categories_loaded = True

    def _load_categories(self) -> list[dict[str, str]]:
        """Load category definitions from file or use defaults."""
        cls_cfg = self._config.get("classification", {})
        cat_file = cls_cfg.get("categories_file", "")

        if cat_file:
            cat_path = Path(cat_file)
            if not cat_path.is_absolute():  # relative to OCR_new, not the current folder
                cat_path = Path(__file__).resolve().parents[1] / cat_path
            if cat_path.exists():
                try:
                    import yaml
                    with open(cat_path, "r", encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    cats = data.get("categories", [])
                    if cats:
                        log.info("Loaded %d categories from '%s'.", len(cats), cat_path)
                        return cats
                except Exception as exc:
                    log.warning("Failed to load categories file: %s", exc)

        log.debug("Using default built-in category definitions.")
        return _DEFAULT_CATEGORIES
