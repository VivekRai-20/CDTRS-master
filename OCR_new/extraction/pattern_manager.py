"""
extraction/pattern_manager.py
------------------------------
Load and validate regex patterns from patterns.yaml.

Each pattern definition may contain:
    patterns  : list[str]   – regex strings (tried in order)
    flags     : list[str]   – re flag names (IGNORECASE, MULTILINE, DOTALL)
    group     : int         – capture group to return (default: 1)
    multiline : bool        – shorthand to add MULTILINE flag

The PatternManager is intentionally read-only — it loads once and returns
compiled patterns on demand.  The RegexEngine does the matching.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from utils.logger import get_logger

log = get_logger(__name__)

# Valid re flag names
_FLAG_MAP: dict[str, int] = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE":  re.MULTILINE,
    "DOTALL":     re.DOTALL,
    "VERBOSE":    re.VERBOSE,
    "ASCII":      re.ASCII,
    "UNICODE":    re.UNICODE,
}


class PatternDefinition:
    """
    Parsed and compiled definition for a single extraction field.

    Attributes
    ----------
    field    : str             — Field name (e.g. "subject")
    patterns : list[re.Pattern]— Compiled regex patterns (in priority order)
    group    : int             — Capture group to return (1 = first group)
    """

    def __init__(
        self,
        field: str,
        raw: list[str],
        flags: int,
        group: int,
    ) -> None:
        self.field = field
        self.group = group
        self.patterns: list[re.Pattern] = []

        for idx, pat_str in enumerate(raw):
            try:
                compiled = re.compile(pat_str, flags)
                self.patterns.append(compiled)
            except re.error as exc:
                log.warning(
                    "Invalid regex for field '%s' pattern %d: %s  — skipped.",
                    field, idx + 1, exc,
                )

    def __repr__(self) -> str:
        return (
            f"<PatternDefinition field='{self.field}' "
            f"patterns={len(self.patterns)} group={self.group}>"
        )


class PatternManager:
    """
    Loads and exposes all field pattern definitions from a YAML file.

    Usage
    -----
    pm = PatternManager("extraction/patterns.yaml")
    pm.load()
    for field, defn in pm.definitions.items():
        ...
    """

    def __init__(self, patterns_file: str | Path) -> None:
        self._path = Path(patterns_file)
        self._definitions: dict[str, PatternDefinition] = {}

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        """
        Parse the patterns YAML file and compile all regex patterns.

        Raises
        ------
        FileNotFoundError – if the YAML file does not exist.
        """
        if not self._path.exists():
            raise FileNotFoundError(
                f"Patterns file not found: {self._path}\n"
                "Create or restore extraction/patterns.yaml."
            )

        with open(self._path, "r", encoding="utf-8") as fh:
            raw_yaml: dict[str, Any] = yaml.safe_load(fh) or {}

        self._definitions = {}

        for field, spec in raw_yaml.items():
            if spec is None:
                log.warning("Field '%s' has no spec — skipped.", field)
                continue

            raw_patterns: list[str] = spec.get("patterns", [])
            group: int = int(spec.get("group", 1))

            # Accumulate flags
            combined_flags = 0
            for flag_name in spec.get("flags", []):
                flag_name_upper = flag_name.upper()
                if flag_name_upper in _FLAG_MAP:
                    combined_flags |= _FLAG_MAP[flag_name_upper]
                else:
                    log.warning("Unknown flag '%s' for field '%s'", flag_name, field)

            if spec.get("multiline", False):
                combined_flags |= re.MULTILINE

            self._definitions[field] = PatternDefinition(
                field=field,
                raw=raw_patterns,
                flags=combined_flags,
                group=group,
            )
            log.debug(
                "Loaded field '%s': %d pattern(s), flags=0x%x, group=%d",
                field, len(self._definitions[field].patterns), combined_flags, group,
            )

        log.info("Loaded %d field definition(s) from %s", len(self._definitions), self._path)

    @property
    def definitions(self) -> dict[str, PatternDefinition]:
        """Dict of field_name → PatternDefinition."""
        if not self._definitions:
            log.warning("PatternManager.load() has not been called yet.")
        return self._definitions

    @property
    def fields(self) -> list[str]:
        """Ordered list of field names."""
        return list(self._definitions.keys())

    def reload(self) -> None:
        """Re-read the YAML file (useful during pattern development)."""
        log.info("Reloading patterns from %s", self._path)
        self.load()
