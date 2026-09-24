"""
layout/region_detector.py
--------------------------
Detect and classify text regions on a document page image.

Two modes
---------
1.  **Model-based** (preferred) – Uses a locally stored layout model
    (e.g., a YOLO or Detectron2 model fine-tuned for document layout)
    placed in ``models/layout/``.

2.  **Contour-based heuristic** (fallback, no model needed) – Finds
    connected-component contours on a binarised image and groups them
    into plausible text regions.  Less accurate than a trained model but
    requires no additional downloads.

Region types
------------
HEADER · FOOTER · TITLE · PARAGRAPH · TABLE · FORM · IMAGE ·
SIGNATURE · HANDWRITTEN_NOTE · STAMP · PAGE_NUMBER · TEXT · UNKNOWN
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


class RegionType(str, Enum):
    HEADER          = "HEADER"
    FOOTER          = "FOOTER"
    TITLE           = "TITLE"
    PARAGRAPH       = "PARAGRAPH"
    TABLE           = "TABLE"
    FORM            = "FORM"
    IMAGE           = "IMAGE"
    SIGNATURE       = "SIGNATURE"
    HANDWRITTEN_NOTE = "HANDWRITTEN_NOTE"
    STAMP           = "STAMP"
    PAGE_NUMBER     = "PAGE_NUMBER"
    TEXT            = "TEXT"
    UNKNOWN         = "UNKNOWN"


class RegionDetector:
    """
    Detect layout regions on a page image.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._model = None
        self._use_model = False
        self._load_model_if_available()

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def detect(
        self, image: np.ndarray, page: int = 1
    ) -> list[dict[str, Any]]:
        """
        Detect layout regions in *image*.

        Parameters
        ----------
        image : np.ndarray
            BGR page image.
        page : int
            1-indexed page number, embedded in returned region dicts.

        Returns
        -------
        list[dict] – each dict has::

            {
                "region_id":   int,
                "page":        int,
                "bbox":        [x1, y1, x2, y2],
                "region_type": str,
                "confidence":  float
            }
        """
        if self._use_model and self._model is not None:
            return self._model_detect(image, page)
        return self._contour_detect(image, page)

    # ------------------------------------------------------------------ #
    # Model loading                                                        #
    # ------------------------------------------------------------------ #

    def _load_model_if_available(self) -> None:
        """Try to load a local layout model."""
        layout_cfg = self._config.get("layout", {})
        model_dir = Path(
            layout_cfg.get("model_path", "models/layout")
        )

        model_file = model_dir / "layout_model.pkl"
        if not model_file.exists():
            log.debug(
                "No layout model found at '%s'. Using contour heuristic.", model_file
            )
            return

        try:
            import pickle
            with open(model_file, "rb") as fh:
                self._model = pickle.load(fh)
            self._use_model = True
            log.info("Loaded layout model from '%s'.", model_file)
        except Exception as exc:
            log.warning("Failed to load layout model: %s", exc)

    # ------------------------------------------------------------------ #
    # Contour-based heuristic                                              #
    # ------------------------------------------------------------------ #

    def _contour_detect(
        self, image: np.ndarray, page: int
    ) -> list[dict[str, Any]]:
        """
        Heuristic layout detection using morphological operations and
        contour analysis.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Dilate horizontally to merge words into lines, then lines into blocks
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
        dilated = cv2.dilate(binary, h_kernel)
        dilated = cv2.dilate(dilated, v_kernel)

        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        img_h, img_w = image.shape[:2]
        regions: list[dict[str, Any]] = []

        for idx, contour in enumerate(contours, start=1):
            x, y, w, h = cv2.boundingRect(contour)

            # Filter very small regions (noise)
            if w < 20 or h < 10:
                continue

            region_type = _classify_region_heuristic(
                x, y, w, h, img_w, img_h
            )
            regions.append(
                {
                    "region_id":   idx,
                    "page":        page,
                    "bbox":        [x, y, x + w, y + h],
                    "region_type": region_type.value,
                    "confidence":  0.60,
                }
            )

        log.debug(
            "Contour detector found %d region(s) on page %d.", len(regions), page
        )
        return regions

    # ------------------------------------------------------------------ #
    # Model-based detection                                                #
    # ------------------------------------------------------------------ #

    def _model_detect(
        self, image: np.ndarray, page: int
    ) -> list[dict[str, Any]]:
        """Placeholder for a trained layout detection model."""
        # This is where a YOLO / Detectron2 / LayoutLM model would run.
        # Falls back to contour heuristic if model inference is not implemented.
        log.debug("Model-based layout detection is not yet implemented; using heuristic.")
        return self._contour_detect(image, page)


# ──────────────────────────────────────────────────────────────────────────────
# Region type heuristic
# ──────────────────────────────────────────────────────────────────────────────

def _classify_region_heuristic(
    x: int, y: int, w: int, h: int, img_w: int, img_h: int
) -> RegionType:
    """
    Assign a region type based on position and size within the page.

    This is a simple position-based heuristic.  A trained model would be
    more accurate.
    """
    # Relative position
    rel_y = y / max(img_h, 1)
    rel_h = h / max(img_h, 1)
    rel_w = w / max(img_w, 1)

    if rel_y < 0.08 and rel_w > 0.4:
        return RegionType.HEADER

    if rel_y > 0.90 and rel_w > 0.4:
        return RegionType.FOOTER

    if rel_y < 0.20 and rel_h < 0.05 and rel_w > 0.2:
        return RegionType.TITLE

    if rel_h < 0.03 and rel_w < 0.15 and rel_y > 0.85:
        return RegionType.PAGE_NUMBER

    if rel_w > 0.5 and rel_h > 0.1:
        return RegionType.PARAGRAPH

    return RegionType.TEXT
