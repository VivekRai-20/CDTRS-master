"""
nlp/ner_engine.py
------------------
Named Entity Recognition using a locally stored model.

Two backends are supported (in priority order):
1.  **spaCy** — uses a locally installed spaCy model (e.g. en_core_web_sm
    installed from a local wheel, or any custom model placed under
    ``models/ner/``).
2.  **Regex fallback** — rule-based extraction for common entity types
    (DATE, EMAIL, PHONE, MONEY, REFERENCE_NUMBER) that works with zero
    additional models.

Model storage
-------------
Place a spaCy-compatible model directory under::

    models/ner/

e.g.::

    models/ner/en_core_web_sm-3.7.1/

Configuration
-------------
::

    ner:
      enabled: true
      model_path: "models/ner"
      backend: "spacy"   # "spacy" | "regex"

Supported entity types
----------------------
PERSON · ORGANIZATION · LOCATION · DATE · TIME · MONEY ·
EMAIL · PHONE · PROJECT · DEPARTMENT · DOCUMENT_ID · REFERENCE_NUMBER
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


class NEREngine:
    """
    Named entity recognition engine.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._nlp = None
        self._backend = "regex"
        self._initialized = False

    # ------------------------------------------------------------------ #
    # Life-cycle                                                           #
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """Load the NER model."""
        ner_cfg = self._config.get("ner", {})

        if not ner_cfg.get("enabled", True):
            log.info("NER engine is DISABLED in config.")
            return

        preferred = str(ner_cfg.get("backend", "spacy")).lower()

        if preferred == "spacy":
            self._try_load_spacy(ner_cfg)

        if self._backend == "regex":
            log.info("NER engine using regex fallback backend.")

        self._initialized = True

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def extract(self, text: str) -> list[dict[str, Any]]:
        """
        Extract named entities from *text*.

        Parameters
        ----------
        text : str
            Cleaned OCR text.

        Returns
        -------
        list[dict] each with::

            {
                "text":       str,
                "label":      str,
                "start":      int,   # character offset in text
                "end":        int,
                "confidence": float
            }
        """
        if not self._initialized:
            self.initialize()

        if not text.strip():
            return []

        if self._backend == "spacy" and self._nlp is not None:
            return self._spacy_extract(text)
        return self._regex_extract(text)

    # ------------------------------------------------------------------ #
    # spaCy backend                                                        #
    # ------------------------------------------------------------------ #

    def _try_load_spacy(self, ner_cfg: dict) -> None:
        model_path = Path(ner_cfg.get("model_path", "models/ner")).resolve()
        try:
            import spacy  # type: ignore

            # Find any subdirectory that looks like a spaCy model
            model_dir = None
            if model_path.exists():
                for child in model_path.iterdir():
                    if child.is_dir() and (child / "meta.json").exists():
                        model_dir = child
                        break

            if model_dir is None:
                log.debug("No spaCy model found in '%s'. Using regex backend.", model_path)
                return

            self._nlp = spacy.load(str(model_dir))
            self._backend = "spacy"
            log.info("NER engine loaded spaCy model from '%s'.", model_dir)

        except ImportError:
            log.debug("spaCy not installed. Using regex NER backend.")
        except Exception as exc:
            log.warning("Failed to load spaCy model: %s. Using regex backend.", exc)

    def _spacy_extract(self, text: str) -> list[dict[str, Any]]:
        doc = self._nlp(text)
        entities: list[dict[str, Any]] = []
        for ent in doc.ents:
            entities.append(
                {
                    "text":       ent.text.strip(),
                    "label":      ent.label_,
                    "start":      ent.start_char,
                    "end":        ent.end_char,
                    "confidence": 0.85,
                }
            )

        # Augment with regex patterns not covered by spaCy
        regex_results = self._regex_extract(text)
        covered = {(e["start"], e["end"]) for e in entities}
        for r in regex_results:
            if (r["start"], r["end"]) not in covered:
                entities.append(r)

        return entities

    # ------------------------------------------------------------------ #
    # Regex backend                                                        #
    # ------------------------------------------------------------------ #

    _PATTERNS: list[tuple[str, str, float]] = [
        # (pattern, label, confidence)
        (
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b",
            "EMAIL", 0.98,
        ),
        (
            r"(?:\+?\d[\d\s\-().]{7,14}\d)",
            "PHONE", 0.80,
        ),
        (
            r"\b(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"[\s,]+\d{1,2}(?:[\s,]+\d{2,4})?\b"
            r"|\b\d{1,2}[\s,]+(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"(?:[\s,]+\d{2,4})?\b"
            r"|\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b"
            r"|\b\d{4}[/\-]\d{2}[/\-]\d{2}\b",
            "DATE", 0.85,
        ),
        (
            r"(?:Rs\.?|INR|USD|\$|€|£)\s*[\d,]+(?:\.\d{1,2})?",
            "MONEY", 0.88,
        ),
        (
            r"\b(?:Ref(?:erence)?\.?\s*(?:No\.?|Number)?[\s:]+|REF[\s:]+)"
            r"[A-Z0-9\-/]{3,20}\b",
            "REFERENCE_NUMBER", 0.82,
        ),
        (
            r"\b(?:Doc(?:ument)?\.?\s*(?:No\.?|ID|Number)?[\s:]+)"
            r"[A-Z0-9\-/]{3,20}\b",
            "DOCUMENT_ID", 0.80,
        ),
    ]

    def _regex_extract(self, text: str) -> list[dict[str, Any]]:
        """Extract entities using compiled regex patterns."""
        entities: list[dict[str, Any]] = []
        seen_spans: set[tuple[int, int]] = set()

        for pattern, label, confidence in self._PATTERNS:
            for match in re.finditer(pattern, text):
                span = (match.start(), match.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                entities.append(
                    {
                        "text":       match.group().strip(),
                        "label":      label,
                        "start":      match.start(),
                        "end":        match.end(),
                        "confidence": confidence,
                    }
                )

        entities.sort(key=lambda e: e["start"])
        return entities
