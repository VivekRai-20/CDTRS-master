"""
nlp/text_cleaner.py
--------------------
Clean and normalise raw OCR text before NLP processing.

OCR output can contain:
  * Repeated whitespace / newlines
  * Hyphenated line-breaks
  * Stray punctuation and symbols
  * Common OCR substitution errors (0 ↔ O, 1 ↔ l, etc.)
  * Encoding artefacts

This module applies a configurable sequence of cleaning steps to produce
cleaner text for downstream NLP and extraction stages.
"""

from __future__ import annotations

import re
import unicodedata

from utils.logger import get_logger

log = get_logger(__name__)

# Common OCR character-substitution corrections
# Maps (wrong_pattern, replacement)
_OCR_CORRECTIONS: list[tuple[str, str]] = [
    (r"\b0(?=[a-zA-Z])", "O"),       # Leading 0 before letters → O
    (r"(?<=[a-zA-Z])0\b", "O"),       # Trailing 0 after letters → O
    (r"\b1(?=[a-zA-Z]{2})", "I"),     # Leading 1 before word chars → I
]


def clean(text: str, config: dict | None = None) -> str:
    """
    Apply OCR text cleaning to *text*.

    Cleaning steps (all enabled by default):
    1.  Unicode normalisation (NFC).
    2.  Remove non-printable / control characters.
    3.  Rejoin hyphenated line-breaks (word- \\n break → word break).
    4.  Normalise whitespace (collapse runs of spaces/tabs).
    5.  Remove blank lines beyond one consecutive blank.
    6.  Strip leading / trailing whitespace.

    Parameters
    ----------
    text : str
        Raw OCR text.
    config : dict, optional
        Application config.  Currently unused (reserved for future flags).

    Returns
    -------
    str
        Cleaned text.
    """
    if not text:
        return ""

    # 1. Unicode normalisation
    text = unicodedata.normalize("NFC", text)

    # 2. Remove non-printable / control characters (keep \\n and \\t)
    text = re.sub(r"[^\x09\x0a\x20-\x7e\x80-\xff]", " ", text)

    # 3. Rejoin hyphenated line-breaks
    text = re.sub(r"-\s*\n\s*", "", text)

    # 4. Normalise whitespace within lines
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]

    # 5. Collapse multiple consecutive blank lines into one
    cleaned_lines: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        cleaned_lines.append(line)
        prev_blank = is_blank

    # 6. Strip overall
    return "\n".join(cleaned_lines).strip()


def remove_ocr_artifacts(text: str) -> str:
    """
    Apply common OCR character-error corrections.

    This is optional and should be used carefully, as aggressive
    correction can introduce new errors.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """
    for pattern, replacement in _OCR_CORRECTIONS:
        text = re.sub(pattern, replacement, text)
    return text


def split_sentences(text: str) -> list[str]:
    """
    Split *text* into sentences for sentence-level processing.

    Uses a simple regex split on sentence-ending punctuation.
    For better accuracy, consider installing and using spaCy's sentencizer.

    Parameters
    ----------
    text : str

    Returns
    -------
    list[str]  – non-empty sentence strings
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]
