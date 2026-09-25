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
The installed ``en_core_web_sm`` package (requirements.txt) is used by
default.  A different spaCy model can be placed in a folder under::

    models/ner/          e.g. models/ner/my_model/  (a folder with meta.json)

which then takes priority.

Configuration
-------------
::

    ner:
      enabled: true
      model_path: "models/ner"
      package: "en_core_web_sm"
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
        """Load spaCy: a model folder under models/ner/ first, then the
        installed model package (en_core_web_sm, in requirements.txt).
        Nothing is downloaded; without either, the regex backend is used."""
        root = Path(__file__).resolve().parents[1]
        model_path = Path(ner_cfg.get("model_path", "models/ner"))
        model_path = model_path if model_path.is_absolute() else root / model_path
        try:
            import spacy  # type: ignore
        except ImportError:
            log.debug("spaCy not installed. Using regex NER backend.")
            return

        candidates: list[str] = []
        if model_path.exists():
            candidates += [
                str(child) for child in sorted(model_path.iterdir())
                if child.is_dir() and (child / "meta.json").exists()
            ]
        package = str(ner_cfg.get("package", "en_core_web_sm") or "").strip()
        if package:
            candidates.append(package)

        for candidate in candidates:
            try:
                # Only the named-entity parts are needed.
                self._nlp = spacy.load(candidate, exclude=["lemmatizer", "textcat"])
            except Exception as exc:
                self._nlp = None
                if candidate == package:
                    try:  # installed package without pip metadata
                        import importlib
                        self._nlp = importlib.import_module(package).load(exclude=["lemmatizer", "textcat"])
                    except Exception:
                        pass
                if self._nlp is None:
                    log.debug("spaCy model '%s' not usable: %s", candidate, exc)
                    continue
            self._backend = "spacy"
            log.info("NER engine loaded spaCy model '%s'.", candidate)
            return
        log.debug("No spaCy model found (%s). Using regex backend.", model_path)

    # spaCy labels worth reporting; the rest (CARDINAL, ORDINAL, NORP, ...)
    # only add noise to the extracted fields.
    _SPACY_LABELS = {"PERSON", "ORG", "GPE", "LOC", "DATE", "TIME", "MONEY"}

    @staticmethod
    def _plausible(label: str, value: str) -> bool:
        """Drop entities the small English model gets wrong on OCR text:
        URLs, numbers read as names, durations read as dates, and so on."""
        if "://" in value or "@" in value or len(value) > 80:
            return False
        words = value.replace(".", ". ").split()
        if label in ("DATE", "TIME", "MONEY"):
            if not any(ch.isdigit() for ch in value):
                return False  # "annual", "today"
            return not re.search(r"\b(years?|months?|weeks?|days?|hours?)\b", value, re.IGNORECASE)
        if any(ch.isdigit() for ch in value):
            return False
        if label == "PERSON":
            return 1 <= len(words) <= 5 and all(w[:1].isalpha() and w[:1].isupper() for w in words)
        return len(words) <= 8

    def _spacy_extract(self, text: str) -> list[dict[str, Any]]:
        doc = self._nlp(text)
        entities: list[dict[str, Any]] = []
        for ent in doc.ents:
            if ent.label_ not in self._SPACY_LABELS:
                continue
            # OCR text has line breaks; an entity never continues past one.
            value = ent.text.split("\n")[0].strip(" ,;:")
            if len(value) < 2:
                continue
            if not self._plausible(ent.label_, value):
                continue
            entities.append(
                {
                    "text":       value,
                    "label":      ent.label_,
                    "start":      ent.start_char,
                    "end":        ent.start_char + len(ent.text.split("\n")[0]),
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
