"""
extraction/date_utils.py
------------------------
Strict date recognition for OCR text.

OCR text is full of things that *look* like dates: reference numbers such as
``44/88/2026``, file numbers ``12-345-2026``, phone fragments.  A value is only
treated as a date when it is a real calendar date (day 1-31 that exists in its
month, month 1-12, a plausible year).

Numeric dates are read day-first (Indian / British usage) unless the first
number cannot be a month-day pair that way round (``03/25/2026`` is read as
25 March because 25 cannot be a month).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

MIN_YEAR = 1950
MAX_YEAR = 2100

_NUMERIC_DMY = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})\s*$")
_NUMERIC_YMD = re.compile(r"^\s*(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*$")
_DAY_MONTH_YEAR = re.compile(
    r"^\s*(\d{1,2})(?:st|nd|rd|th)?\s*[\-/ ]?\s*([A-Za-z]{3,9})\.?\s*[,\-/ ]?\s*(\d{2}|\d{4})\s*$",
    re.IGNORECASE,
)
_MONTH_DAY_YEAR = re.compile(
    r"^\s*([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\s*$",
    re.IGNORECASE,
)


def _year(value: str) -> int:
    y = int(value)
    return 2000 + y if len(value) == 2 else y


def _build(y: int, m: int, d: int) -> Optional[date]:
    if not (MIN_YEAR <= y <= MAX_YEAR):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: Optional[str]) -> Optional[date]:
    """The calendar date *text* denotes, or None when it is not a real date."""
    if not text:
        return None
    s = str(text).strip().rstrip(".,;:")
    if not s:
        return None

    m = _NUMERIC_YMD.match(s)
    if m:
        return _build(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _NUMERIC_DMY.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        if b <= 12:
            parsed = _build(y, b, a)          # day-first
            if parsed:
                return parsed
        if a <= 12:
            return _build(y, a, b)            # month-first (e.g. 03/25/2026)
        return None

    m = _DAY_MONTH_YEAR.match(s)
    if m:
        month = _MONTHS.get(m.group(2).lower())
        if month:
            return _build(_year(m.group(3)), month, int(m.group(1)))
        return None

    m = _MONTH_DAY_YEAR.match(s)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            return _build(int(m.group(3)), month, int(m.group(2)))
        return None

    return None


def is_valid_date(text: Optional[str]) -> bool:
    return parse_date(text) is not None


def to_iso(text: Optional[str]) -> str:
    """``YYYY-MM-DD`` for a real date, else an empty string."""
    parsed = parse_date(text)
    return parsed.isoformat() if parsed else ""
