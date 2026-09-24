"""
nlp/entity_normalizer.py
-------------------------
Normalise raw entity text extracted by the NER engine.

Different surface forms of the same entity are standardised:

  Dates       "20 September" → "2026-09-20"  (ISO 8601 where possible)
  Phone       "+91 98765 43210" → "+919876543210"
  Email       "  User@EXAMPLE.COM  " → "user@example.com"
  Money       "Rs. 1,000" → "INR 1000"  (simple normalisation)
  Numbers     "one thousand" → "1000"  (not yet implemented — placeholder)

Unknown entity types are returned as-is (stripped of extra whitespace).
"""

from __future__ import annotations

import re
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


def normalize_entity(text: str, label: str) -> str:
    """
    Normalise a single entity *text* according to its *label*.

    Parameters
    ----------
    text : str
        Raw entity string as extracted by NER.
    label : str
        Entity label (e.g. "DATE", "PHONE", "EMAIL", "MONEY", …).

    Returns
    -------
    str
        Normalised entity string.
    """
    text = text.strip()

    normalizers = {
        "DATE":   _normalize_date,
        "PHONE":  _normalize_phone,
        "EMAIL":  _normalize_email,
        "MONEY":  _normalize_money,
    }

    handler = normalizers.get(label.upper())
    if handler is not None:
        try:
            return handler(text)
        except Exception as exc:
            log.debug("Entity normalisation failed for '%s' (%s): %s", text, label, exc)

    return text


def normalize_entities(
    entities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Normalise a list of entity dicts in-place and return them.

    Each dict is expected to have ``text`` and ``label`` keys.
    A ``normalized_text`` key is added.

    Parameters
    ----------
    entities : list[dict]

    Returns
    -------
    list[dict]
    """
    for ent in entities:
        raw = ent.get("text", "")
        label = ent.get("label", "")
        ent["normalized_text"] = normalize_entity(raw, label)
    return entities


# ──────────────────────────────────────────────────────────────────────────────
# Normaliser functions
# ──────────────────────────────────────────────────────────────────────────────

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _normalize_date(text: str) -> str:
    """Attempt to convert a date string to YYYY-MM-DD format."""
    # Try dateutil if available (offline)
    try:
        from dateutil import parser as dateparser  # type: ignore
        dt = dateparser.parse(text, dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Manual parsing: "20 September", "September 20, 2024"
    text_lower = text.lower()
    for month_name, month_num in _MONTH_MAP.items():
        if month_name in text_lower:
            day_match = re.search(r"\b(\d{1,2})\b", text)
            year_match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
            day = int(day_match.group(1)) if day_match else 1
            year = int(year_match.group(1)) if year_match else 2026
            return f"{year:04d}-{month_num:02d}-{day:02d}"

    return text  # Return original if can't parse


def _normalize_phone(text: str) -> str:
    """Strip all non-digit characters except leading +."""
    digits = re.sub(r"[^\d+]", "", text)
    if not digits.startswith("+"):
        digits = re.sub(r"[^\d]", "", text)
    return digits


def _normalize_email(text: str) -> str:
    """Lowercase and strip whitespace."""
    return text.lower().strip()


def _normalize_money(text: str) -> str:
    """Attempt to produce a simple normalised amount string."""
    # Remove thousands separators
    clean = re.sub(r"[\s,]", "", text)
    # Extract numeric value
    numeric = re.search(r"[\d.]+", clean)
    if not numeric:
        return text
    amount = numeric.group()
    # Detect currency symbol/name
    upper = text.upper()
    if "INR" in upper or "RS" in upper or "₹" in text:
        return f"INR {amount}"
    if "USD" in upper or "$" in text:
        return f"USD {amount}"
    if "EUR" in upper or "€" in text:
        return f"EUR {amount}"
    return amount
