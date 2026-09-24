"""
classification/semantic_classifier.py
--------------------------------------
Semantic similarity-based document classifier.

Wraps ``SemanticDocumentClassifier`` from the ``semantic/`` package and
adapts it to the ``BaseClassifier`` interface.
"""

from __future__ import annotations

from typing import Any

from classification.base_classifier import BaseClassifier
from utils.logger import get_logger

log = get_logger(__name__)


class SemanticClassifier(BaseClassifier):
    """
    Classify documents using embedding-based semantic similarity.

    Requires a local embedding model under ``models/embeddings/``.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    CLASSIFIER_NAME = "SemanticClassifier"

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._inner = None  # Lazy-loaded on first use

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def classify(self, text: str) -> dict[str, Any]:
        """
        Classify *text* semantically.

        Falls back to UNKNOWN with confidence 0 if the embedding model
        is unavailable.
        """
        if not text.strip():
            return self._result("UNKNOWN", 0.0)

        try:
            inner = self._get_inner()
            sem_result = inner.classify(text)
            return self._result(
                sem_result.get("label", "UNKNOWN"),
                sem_result.get("confidence", 0.0),
            )
        except Exception as exc:
            log.warning("SemanticClassifier failed: %s", exc)
            return self._result("UNKNOWN", 0.0)

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _get_inner(self):
        if self._inner is None:
            from semantic.embedding_engine import EmbeddingEngine
            from semantic.document_classifier import SemanticDocumentClassifier

            engine = EmbeddingEngine(config=self._config)
            engine.initialize()
            self._inner = SemanticDocumentClassifier(
                embedding_engine=engine, config=self._config
            )
        return self._inner
