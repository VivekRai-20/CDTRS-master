"""
extraction/entity_extractor.py
-------------------------------
Combines NER and regex extraction to produce structured field values
from OCR text.

This module bridges the gap between raw NER entity lists and the
``extracted_fields`` section of the standardised output.

Strategy
--------
1.  Run ``NEREngine.extract()`` to get all raw entities.
2.  Normalise entities with ``entity_normalizer``.
3.  Combine with any regex-pattern results from ``regex_engine``.
4.  Deduplicate and return a structured dict of field → value(s).
"""

from __future__ import annotations

from typing import Any

from nlp.ner_engine import NEREngine
from nlp.entity_normalizer import normalize_entities
from utils.logger import get_logger

log = get_logger(__name__)

# Map NER label → extracted_fields key
_LABEL_TO_FIELD: dict[str, str] = {
    "PERSON":           "persons",
    "ORG":              "organizations",
    "ORGANIZATION":     "organizations",
    "GPE":              "locations",
    "LOCATION":         "locations",
    "LOC":              "locations",
    "DATE":             "dates",
    "TIME":             "times",
    "MONEY":            "amounts",
    "EMAIL":            "emails",
    "PHONE":            "phone_numbers",
    "PROJECT":          "projects",
    "DEPARTMENT":       "departments",
    "DOCUMENT_ID":      "document_ids",
    "REFERENCE_NUMBER": "reference_numbers",
}


class EntityExtractor:
    """
    Extracts and structures named entities from OCR text.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._ner = NEREngine(config=self._config)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def extract(self, text: str) -> dict[str, Any]:
        """
        Extract all entities and return a structured result.

        Parameters
        ----------
        text : str
            Cleaned OCR text.

        Returns
        -------
        dict::

            {
                "entities": list[dict],         # raw entity list
                "extracted_fields": dict        # field_name → list[str]
            }
        """
        raw_entities = self._ner.extract(text)
        normalised = normalize_entities(raw_entities)

        extracted_fields: dict[str, list[str]] = {}
        for ent in normalised:
            label = ent.get("label", "").upper()
            field_key = _LABEL_TO_FIELD.get(label)
            if field_key is None:
                field_key = label.lower() if label else "unknown"

            value = ent.get("normalized_text") or ent.get("text", "")
            if value:
                extracted_fields.setdefault(field_key, [])
                if value not in extracted_fields[field_key]:
                    extracted_fields[field_key].append(value)

        log.debug(
            "EntityExtractor: %d raw entities → %d field types.",
            len(normalised), len(extracted_fields),
        )
        return {
            "entities": normalised,
            "extracted_fields": extracted_fields,
        }
