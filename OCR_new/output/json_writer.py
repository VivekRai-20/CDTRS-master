"""
output/json_writer.py
----------------------
Write the standardised result dict to a JSON file.

Output path
-----------
For input ``input/document.pdf`` the output will be placed at::

    output/document/result.json

and individual component files::

    output/document/ocr.json
    output/document/layout.json
    output/document/entities.json
    output/document/semantic.json
    output/document/classification.json
    output/document/extracted.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


class JSONWriter:
    """
    Write processing results as JSON files.

    Parameters
    ----------
    output_dir : str or Path
        Root output directory (default: "output").
    """

    def __init__(self, output_dir: str | Path = "output") -> None:
        self._output_dir = Path(output_dir)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def write(self, result: dict[str, Any], document_name: str) -> Path:
        """
        Write the full standardised *result* dict as JSON.

        Parameters
        ----------
        result : dict
            The complete processing result.
        document_name : str
            Used as the output subdirectory name (e.g. "document" for
            "document.pdf").

        Returns
        -------
        Path
            Path to the written ``result.json`` file.
        """
        doc_dir = self._ensure_dir(document_name)

        # Write monolithic result
        result_path = doc_dir / "result.json"
        self._write_json(result, result_path)

        # Write individual component files
        self._write_component(result.get("ocr"), doc_dir / "ocr.json")
        self._write_component(result.get("layout"), doc_dir / "layout.json")
        self._write_component(result.get("text_types"), doc_dir / "text_types.json")
        self._write_component(result.get("entities"), doc_dir / "entities.json")
        self._write_component(result.get("semantic"), doc_dir / "semantic.json")
        self._write_component(result.get("classification"), doc_dir / "classification.json")
        self._write_component(result.get("extracted_fields"), doc_dir / "extracted.json")

        log.info("JSON output written to '%s'.", doc_dir)
        return result_path

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _ensure_dir(self, document_name: str) -> Path:
        # Strip extension from document name
        name = Path(document_name).stem
        doc_dir = self._output_dir / name
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir

    @staticmethod
    def _write_json(data: Any, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)

    def _write_component(self, data: Any, path: Path) -> None:
        if data is None:
            return
        self._write_json(data, path)
