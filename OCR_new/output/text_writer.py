"""
output/text_writer.py
----------------------
Write plain OCR text to ``output/<docname>/ocr.txt``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


class TextWriter:
    """
    Write the extracted OCR text as a plain ``ocr.txt`` file.

    Parameters
    ----------
    output_dir : str or Path
        Root output directory (default: "output").
    """

    def __init__(self, output_dir: str | Path = "output") -> None:
        self._output_dir = Path(output_dir)

    def write(self, result: dict[str, Any], document_name: str) -> Path:
        """
        Write plain text from *result* to ``ocr.txt``.

        Parameters
        ----------
        result : dict
            Full processing result dict; the ``full_text`` or
            ``ocr.full_text`` key is used.
        document_name : str
            Used as the output subdirectory name.

        Returns
        -------
        Path to the written ``ocr.txt`` file.
        """
        name = Path(document_name).stem
        doc_dir = self._output_dir / name
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Resolve full text from multiple possible locations in the result
        full_text = (
            result.get("full_text")
            or result.get("text")
            or result.get("ocr", {}).get("full_text")
            or result.get("ocr", {}).get("text", "")
        )

        txt_path = doc_dir / "ocr.txt"
        txt_path.write_text(full_text or "", encoding="utf-8")
        log.info("Plain text output written to '%s'.", txt_path)
        return txt_path
