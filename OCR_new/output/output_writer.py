"""
output/output_writer.py
------------------------
Write OCR and extraction results to the output directory.

Output structure (per input file)
----------------------------------
output/
└── <basename>/
    ├── ocr.txt          – plain extracted text
    ├── ocr.json         – structured per-region OCR data
    ├── extracted.json   – regex-matched field values  (full mode only)
    └── result.json      – combined summary             (full mode only)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

log = get_logger(__name__)


class OutputWriter:
    """
    Manages all output artefacts for one processed document.

    Parameters
    ----------
    input_file : str or Path
        The original input file path (used to derive the output sub-dir).
    config : dict
        Full application config dict.
    """

    def __init__(self, input_file: str | Path, config: dict) -> None:
        self._input_path = Path(input_file)
        self._config = config

        out_cfg   = config.get("output", {})
        paths_cfg = config.get("paths", {})

        root = Path(__file__).resolve().parents[1]
        output_root = root / paths_cfg.get("output_dir", "output")

        # Sub-directory named after the input file stem
        self._out_dir: Path = output_root / self._input_path.stem
        self._out_dir.mkdir(parents=True, exist_ok=True)

        self._indent: int = int(out_cfg.get("json_indent", 2))

        log.debug("Output directory: %s", self._out_dir)

    # ------------------------------------------------------------------ #
    # Write helpers                                                        #
    # ------------------------------------------------------------------ #

    def write_ocr(self, ocr_result: dict[str, Any]) -> dict[str, Path]:
        """
        Write OCR outputs: ocr.txt and ocr.json.

        Parameters
        ----------
        ocr_result : dict
            The dict returned by OCRPipeline.process().

        Returns
        -------
        dict of {filename: Path}
        """
        written: dict[str, Path] = {}

        # --- ocr.txt --------------------------------------------------- #
        txt_path = self._out_dir / "ocr.txt"
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(ocr_result.get("full_text", ""))
        log.info("Wrote: %s", txt_path)
        written["ocr.txt"] = txt_path

        # --- ocr.json -------------------------------------------------- #
        json_path = self._out_dir / "ocr.json"
        payload = {
            "file":         ocr_result["file"],
            "doc_type":     ocr_result["doc_type"],
            "pages":        ocr_result["pages"],
            "elapsed_s":    ocr_result["elapsed_s"],
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "regions":      ocr_result["regions"],
        }
        _write_json(json_path, payload, self._indent)
        log.info("Wrote: %s", json_path)
        written["ocr.json"] = json_path

        return written

    def write_extracted(
        self,
        extraction_results: dict[str, Any],
    ) -> dict[str, Path]:
        """
        Write extraction output: extracted.json.

        Parameters
        ----------
        extraction_results : dict
            Dict of field_name → ExtractionResult (or plain str/None).

        Returns
        -------
        dict of {filename: Path}
        """
        written: dict[str, Path] = {}

        ext_path = self._out_dir / "extracted.json"

        # Normalise to serialisable form
        payload: dict[str, Any] = {}
        for field, result in extraction_results.items():
            if hasattr(result, "to_dict"):
                payload[field] = result.to_dict()
            else:
                payload[field] = {"field": field, "value": result,
                                  "matched_by": None, "pattern_str": None}

        _write_json(ext_path, payload, self._indent)
        log.info("Wrote: %s", ext_path)
        written["extracted.json"] = ext_path

        return written

    def write_result(
        self,
        ocr_result: dict[str, Any],
        extraction_results: dict[str, Any],
    ) -> dict[str, Path]:
        """
        Write the combined result.json summary.
        """
        written: dict[str, Path] = {}

        result_path = self._out_dir / "result.json"

        simple_extracted = {
            field: (result.value if hasattr(result, "value") else result)
            for field, result in extraction_results.items()
        }

        payload = {
            "file":         ocr_result["file"],
            "doc_type":     ocr_result["doc_type"],
            "pages":        ocr_result["pages"],
            "elapsed_s":    ocr_result["elapsed_s"],
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "extracted":    simple_extracted,
            "ocr_region_count": len(ocr_result["regions"]),
        }

        _write_json(result_path, payload, self._indent)
        log.info("Wrote: %s", result_path)
        written["result.json"] = result_path

        return written

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def output_dir(self) -> Path:
        return self._out_dir


# =========================================================================== #
# Utility                                                                      #
# =========================================================================== #

def _write_json(path: Path, data: Any, indent: int) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False, default=str)
