"""
layout/layout_analyzer.py
--------------------------
Orchestrates the full layout analysis stage.

Pipeline
--------
  Page image
      ↓  RegionDetector.detect()   – find bounding boxes + initial types
      ↓  assign_reading_order()    – reconstruct logical reading order
      ↓  return list[LayoutRegion]

The output is a list of region dicts that the rest of the pipeline
(OCR, text-type detection, semantic, …) can consume directly.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from layout.region_detector import RegionDetector
from layout.reading_order import assign_reading_order
from utils.logger import get_logger

log = get_logger(__name__)


class LayoutAnalyzer:
    """
    High-level coordinator for layout analysis on one or more pages.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._enabled: bool = self._config.get("layout", {}).get("enabled", True)
        self._detector = RegionDetector(config=self._config)

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def analyze_page(
        self, image: np.ndarray, page: int = 1
    ) -> list[dict[str, Any]]:
        """
        Run layout analysis on a single page image.

        Parameters
        ----------
        image : np.ndarray
            BGR page image.
        page : int
            1-indexed page number.

        Returns
        -------
        list[dict]
            Layout region dicts with reading_order assigned::

                {
                    "region_id":    int,
                    "page":         int,
                    "bbox":         [x1, y1, x2, y2],
                    "region_type":  str,
                    "confidence":   float,
                    "reading_order": int
                }
        """
        if not self._enabled:
            log.debug("Layout analysis is DISABLED in config.")
            return []

        regions = self._detector.detect(image, page=page)
        regions = assign_reading_order(regions)

        log.debug(
            "Layout: %d region(s) found on page %d.", len(regions), page
        )
        return regions

    def analyze_document(
        self, pages: list[tuple[int, np.ndarray]]
    ) -> list[dict[str, Any]]:
        """
        Run layout analysis across multiple pages.

        Parameters
        ----------
        pages : list of (page_number, image) tuples

        Returns
        -------
        list[dict]
            All regions from all pages, reading_order assigned globally.
        """
        all_regions: list[dict[str, Any]] = []
        for page_num, image in pages:
            page_regions = self._detector.detect(image, page=page_num)
            all_regions.extend(page_regions)

        # Assign global reading order across all pages at once
        all_regions = assign_reading_order(all_regions)
        log.info(
            "Layout analysis complete: %d total region(s) across %d page(s).",
            len(all_regions), len(pages),
        )
        return all_regions
