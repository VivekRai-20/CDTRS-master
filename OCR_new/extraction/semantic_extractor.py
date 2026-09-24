"""
extraction/semantic_extractor.py
---------------------------------
Extract structured fields when meaning matters more than exact wording.

Instead of matching fixed patterns (regex) or surface forms (NER), this
extractor uses embedding similarity to identify which portions of text
correspond to known field types.

Example
-------
Given the OCR text:

    "I would like to inform you that I will be absent for two days
     from 14 September due to a medical appointment."

A semantic query for "leave duration" can match "two days" even though
the exact phrase "leave duration" never appears.

Strategy
--------
For each target field:
1.  Embed the field description (query).
2.  Embed each sentence in the document text.
3.  Return the sentence(s) with highest similarity above a threshold
    as the extracted value.

This is intentionally conservative — it only fires when similarity
exceeds the configured threshold.

Configuration
-------------
::

    extraction:
      semantic_threshold: 0.5
      semantic_fields:
        - field: "leave_duration"
          description: "how many days of leave are requested"
        - field: "reason"
          description: "reason or purpose stated in the document"
"""

from __future__ import annotations

import re
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_THRESHOLD = 0.50

_DEFAULT_FIELDS = [
    {
        "field":       "subject",
        "description": "the main subject or title of the document",
    },
    {
        "field":       "reason",
        "description": "the reason, purpose or justification stated",
    },
    {
        "field":       "duration",
        "description": "the time period or duration mentioned in the document",
    },
    {
        "field":       "action_required",
        "description": "any action that is requested or required from the reader",
    },
]


class SemanticExtractor:
    """
    Field extractor using sentence-level semantic similarity.

    Parameters
    ----------
    embedding_engine : optional
        A ready ``EmbeddingEngine`` instance.  If None, semantic extraction
        is skipped gracefully.
    config : dict
        Full application configuration.
    """

    def __init__(
        self,
        embedding_engine=None,
        config: dict | None = None,
    ) -> None:
        self._engine = embedding_engine
        self._config = config or {}
        ext_cfg = self._config.get("extraction", {})
        self._threshold = float(ext_cfg.get("semantic_threshold", _DEFAULT_THRESHOLD))
        self._fields = ext_cfg.get("semantic_fields", _DEFAULT_FIELDS)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def extract(self, text: str) -> dict[str, Any]:
        """
        Attempt semantic field extraction from *text*.

        Parameters
        ----------
        text : str

        Returns
        -------
        dict mapping field name → extracted sentence (or None)
        """
        if self._engine is None:
            log.debug("SemanticExtractor: no embedding engine — skipping.")
            return {}

        if not text.strip():
            return {}

        sentences = self._split_sentences(text)
        if not sentences:
            return {}

        try:
            sentence_embeddings = self._engine.encode(sentences)
        except Exception as exc:
            log.warning("SemanticExtractor embedding failed: %s", exc)
            return {}

        result: dict[str, Any] = {}

        for field_def in self._fields:
            field_name = field_def.get("field", "unknown")
            description = field_def.get("description", field_name)

            try:
                from semantic.semantic_similarity import cosine_similarity
                import numpy as np

                query_emb = self._engine.encode(description)
                best_score = -1.0
                best_sentence = None

                for idx, sent_emb in enumerate(sentence_embeddings):
                    score = cosine_similarity(query_emb, sent_emb)
                    if score > best_score:
                        best_score = score
                        best_sentence = sentences[idx]

                if best_score >= self._threshold and best_sentence:
                    result[field_name] = {
                        "value":      best_sentence,
                        "similarity": round(best_score, 4),
                    }

            except Exception as exc:
                log.debug("SemanticExtractor field '%s' failed: %s", field_name, exc)

        log.debug(
            "SemanticExtractor: extracted %d/%d fields above threshold %.2f.",
            len(result), len(self._fields), self._threshold,
        )
        return result

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?\n])\s+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]
