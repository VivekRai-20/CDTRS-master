"""
semantic/semantic_pipeline.py
------------------------------
Orchestrates all semantic processing stages for a single document.

Stages
------
1.  Generate document-level embedding.
2.  Extract keywords.
3.  Run semantic document classification.
4.  Compute similarity to any provided reference documents (optional).

Returns a single ``semantic`` result dict that is merged into the
standardised output structure.
"""

from __future__ import annotations

from typing import Any

from semantic.embedding_engine import EmbeddingEngine
from semantic.keyword_extractor import extract_keywords
from semantic.document_classifier import SemanticDocumentClassifier
from semantic.semantic_similarity import cosine_similarity
from utils.logger import get_logger

log = get_logger(__name__)


class SemanticPipeline:
    """
    High-level coordinator for all semantic analysis.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        sem_cfg = self._config.get("semantic", {})
        self._enabled: bool = sem_cfg.get("enabled", True)

        self._embedding_engine: EmbeddingEngine | None = None
        self._classifier: SemanticDocumentClassifier | None = None

        if self._enabled:
            self._embedding_engine = EmbeddingEngine(config=self._config)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def process(
        self,
        text: str,
        reference_texts: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run the full semantic pipeline on *text*.

        Parameters
        ----------
        text : str
            OCR-extracted full text of the document.
        reference_texts : list[str], optional
            Texts to compute similarity against.

        Returns
        -------
        dict::

            {
                "enabled":        bool,
                "embedding":      list[float] | None,
                "keywords":       list[dict],
                "classification": dict,
                "similarities":   list[dict],
            }
        """
        if not self._enabled:
            log.debug("Semantic pipeline is DISABLED in config.")
            return {"enabled": False}

        result: dict[str, Any] = {"enabled": True}

        # Step 1 — Embedding
        embedding = None
        try:
            if self._embedding_engine is None:
                self._embedding_engine = EmbeddingEngine(config=self._config)
            embedding = self._embedding_engine.encode(text[:4096])
            result["embedding"] = embedding.tolist()
        except Exception as exc:
            log.warning("Embedding failed: %s", exc)
            result["embedding"] = None

        # Step 2 — Keywords
        try:
            keywords = extract_keywords(text, top_n=10)
            result["keywords"] = keywords
        except Exception as exc:
            log.warning("Keyword extraction failed: %s", exc)
            result["keywords"] = []

        # Step 3 — Classification
        try:
            if embedding is not None:
                if self._classifier is None:
                    self._classifier = SemanticDocumentClassifier(
                        embedding_engine=self._embedding_engine,  # type: ignore
                        config=self._config,
                    )
                classification = self._classifier.classify(text)
            else:
                classification = {"label": "UNKNOWN", "confidence": 0.0, "categories": []}
            result["classification"] = classification
        except Exception as exc:
            log.warning("Semantic classification failed: %s", exc)
            result["classification"] = {"label": "UNKNOWN", "confidence": 0.0, "categories": []}

        # Step 4 — Similarities to reference texts
        similarities: list[dict[str, Any]] = []
        if embedding is not None and reference_texts:
            for ref_text in reference_texts:
                try:
                    ref_emb = self._embedding_engine.encode(ref_text[:4096])  # type: ignore
                    sim = cosine_similarity(embedding, ref_emb)
                    similarities.append(
                        {"reference": ref_text[:80] + "…", "similarity": round(sim, 4)}
                    )
                except Exception as exc:
                    log.warning("Reference similarity failed: %s", exc)
        result["similarities"] = similarities

        return result
