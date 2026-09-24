"""
extraction/regex_engine.py
---------------------------
Apply PatternManager definitions to extracted text and return
structured field matches.

Design goals
------------
• Never crash when a field is missing — return null.
• Report which pattern matched (for debugging).
• Handle OCR spacing noise through patterns and text normalisation.
• Completely independent of PaddleOCR — takes plain text as input.

Output schema (per field)
-------------------------
{
    "field":         "subject",
    "value":         "Data Mining and Data Warehousing",
    "matched_by":    "Pattern 1",
    "pattern_str":   "Subject\\s*[:\\-]\\s*(.+)",
    "confidence":    null          # reserved for future ML scoring
}
"""

from __future__ import annotations

import re
from typing import Any, Optional

from extraction.pattern_manager import PatternManager, PatternDefinition
from utils.logger import get_logger

log = get_logger(__name__)


class ExtractionResult:
    """
    Result for one extracted field.

    Attributes
    ----------
    field       : field name
    value       : matched string, or None if not found
    matched_by  : human-readable "Pattern N" label, or None
    pattern_str : the raw regex string that matched, or None
    """

    def __init__(
        self,
        field: str,
        value: Optional[str] = None,
        matched_by: Optional[str] = None,
        pattern_str: Optional[str] = None,
    ) -> None:
        self.field       = field
        self.value       = value
        self.matched_by  = matched_by
        self.pattern_str = pattern_str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field":       self.field,
            "value":       self.value,
            "matched_by":  self.matched_by,
            "pattern_str": self.pattern_str,
            "confidence":  None,
        }

    def __repr__(self) -> str:
        return f"<ExtractionResult field='{self.field}' value={self.value!r}>"


class RegexEngine:
    """
    Applies all loaded patterns to a block of text.

    Parameters
    ----------
    manager : PatternManager
        A loaded PatternManager instance.
    """

    def __init__(self, manager: PatternManager) -> None:
        self._manager = manager

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def extract(self, text: str) -> dict[str, ExtractionResult]:
        """
        Extract all configured fields from *text*.

        Parameters
        ----------
        text : str
            Raw OCR output or any plain text.

        Returns
        -------
        dict[str, ExtractionResult]
            Keyed by field name.  Missing fields have value=None.
        """
        # Light normalisation to help patterns survive OCR noise
        normalised = _normalise_ocr_text(text)

        results: dict[str, ExtractionResult] = {}

        for field, defn in self._manager.definitions.items():
            result = self._match_field(normalised, defn)
            results[field] = result
            if result.value:
                log.debug(
                    "  %-20s  %-40s  (%s)",
                    field, result.value[:40], result.matched_by,
                )
            else:
                log.debug("  %-20s  [no match]", field)

        return results

    def extract_to_dict(self, text: str) -> dict[str, Optional[str]]:
        """
        Convenience method: return {field: value_or_None} dict.
        """
        return {f: r.value for f, r in self.extract(text).items()}

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _match_field(text: str, defn: PatternDefinition) -> ExtractionResult:
        """
        Try each compiled pattern for *defn* against *text*.
        Return the first successful match.
        """
        for idx, compiled in enumerate(defn.patterns, start=1):
            match = compiled.search(text)
            if match:
                try:
                    value = match.group(defn.group).strip()
                except IndexError:
                    # Pattern has no capturing group — return the full match
                    value = match.group(0).strip()

                if value:
                    return ExtractionResult(
                        field=defn.field,
                        value=value,
                        matched_by=f"Pattern {idx}",
                        pattern_str=compiled.pattern,
                    )

        return ExtractionResult(field=defn.field)   # value=None

    # ------------------------------------------------------------------ #
    # Display                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_table(results: dict[str, "ExtractionResult"]) -> str:
        """
        Format extraction results as a readable table.

        Example
        -------
        FIELD            VALUE                              PATTERN
        ----------------------------------------------------------------
        subject          Data Mining and Data Warehousing   Pattern 1
        name             Vivek Rai                          Pattern 1
        roll_no          42                                 Pattern 1
        date             18/08/2026                         Pattern 1
        title            [not found]                        —
        """
        col_field   = max((len(f) for f in results), default=10)
        col_field   = max(col_field, 12)
        col_value   = 40
        col_pattern = 15

        header = (
            f"{'FIELD':<{col_field}}  {'VALUE':<{col_value}}  PATTERN"
        )
        sep = "-" * (col_field + col_value + col_pattern + 6)

        lines = [header, sep]
        for field, res in results.items():
            val_str = res.value if res.value else "[not found]"
            pat_str = res.matched_by if res.matched_by else "-"
            lines.append(
                f"{field:<{col_field}}  {val_str[:col_value]:<{col_value}}  {pat_str}"
            )

        return "\n".join(lines)


# =========================================================================== #
# OCR text normalisation                                                       #
# =========================================================================== #

def _normalise_ocr_text(text: str) -> str:
    """
    Light normalisation to improve pattern match rates on OCR output.

    • Collapse multiple spaces to single space
    • Strip trailing whitespace from each line
    • Normalise common OCR character confusions (0↔O, l↔1 etc.) NOT done
      here — would corrupt values; keep it per-field in patterns if needed.
    """
    lines = text.splitlines()
    normalised_lines: list[str] = []
    for line in lines:
        # Collapse internal multiple spaces
        line = re.sub(r"[ \t]{2,}", " ", line)
        line = line.rstrip()
        normalised_lines.append(line)
    return "\n".join(normalised_lines)
