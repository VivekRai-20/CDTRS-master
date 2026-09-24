"""
ocr/base_engine.py
------------------
Abstract base class for all OCR engines.

Design goal
-----------
Every OCR engine (PaddleOCR, future TrOCR, custom handwriting model, …)
must implement this interface.  The rest of the system talks ONLY to
BaseOCREngine — swapping engines requires zero changes to the pipeline.

Result schema (per detected text region)
-----------------------------------------
{
    "text":       str,          # Recognised text
    "confidence": float,        # 0.0 – 1.0
    "bbox":       [x1,y1,x2,y2],# Bounding box in pixel coordinates
    "page":       int,          # 1-indexed page number
}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class BaseOCREngine(ABC):
    """
    Abstract OCR engine.

    Concrete implementations must override ``recognize``.
    """

    # Human-readable engine name (override in subclasses)
    ENGINE_NAME: str = "BaseOCREngine"

    # ------------------------------------------------------------------ #
    # Life-cycle                                                           #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def initialize(self, config: dict) -> None:
        """
        Load / warm-up the engine.  Called once before processing begins.

        Parameters
        ----------
        config : dict
            The full application config dict (from config.yaml).
        """
        ...

    # ------------------------------------------------------------------ #
    # Core recognition                                                     #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def recognize(self, image: np.ndarray, page: int = 1) -> list[dict[str, Any]]:
        """
        Run OCR on a single image.

        Parameters
        ----------
        image : np.ndarray
            BGR image as returned by ``cv2.imread`` (or equivalent).
        page : int
            1-indexed page number to embed in each result record.

        Returns
        -------
        list[dict]
            Each element has the schema described in the module docstring.
        """
        ...

    # ------------------------------------------------------------------ #
    # Helpers available to all subclasses                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def bbox_to_list(bbox: Any) -> list[int]:
        """
        Normalise various bounding-box formats to [x1, y1, x2, y2].

        PaddleOCR returns a polygon: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]].
        This helper converts that to an axis-aligned rectangle.
        """
        if bbox is None:
            return [0, 0, 0, 0]

        import numpy as np

        # Convert numpy arrays to plain Python list first
        if isinstance(bbox, np.ndarray):
            bbox = bbox.tolist()

        arr = list(bbox)
        if not arr:
            return [0, 0, 0, 0]

        # Polygon format: list of [x, y] pairs (or numpy sub-arrays)
        first = arr[0]
        if isinstance(first, (list, tuple, np.ndarray)):
            pts = [list(pt) for pt in arr]
            xs = [int(pt[0]) for pt in pts]
            ys = [int(pt[1]) for pt in pts]
            return [min(xs), min(ys), max(xs), max(ys)]

        # Already a flat 4-element list / tuple
        if len(arr) == 4:
            return [int(v) for v in arr]

        return [0, 0, 0, 0]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} engine='{self.ENGINE_NAME}'>"
