"""
ocr/text_type_detector.py
--------------------------
Classify each text region as PRINTED, HANDWRITTEN, MIXED, or UNKNOWN.

Strategy
--------
1.  If a locally trained classifier model exists under
    ``models/classifiers/text_type/``, it is loaded and used for prediction.
2.  Otherwise, a heuristic based on stroke-width variance and local
    contrast is applied — no model required.

The heuristic is intentionally conservative: when uncertain it returns
UNKNOWN rather than making a wrong prediction.

Output
------
Each call to ``detect`` returns a dict::

    {
        "text_type":  "PRINTED" | "HANDWRITTEN" | "MIXED" | "UNKNOWN",
        "confidence": float   # 0.0 – 1.0
    }
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


class TextType(str, Enum):
    PRINTED     = "PRINTED"
    HANDWRITTEN = "HANDWRITTEN"
    MIXED       = "MIXED"
    UNKNOWN     = "UNKNOWN"


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

class TextTypeDetector:
    """
    Detects whether a text image region is printed, handwritten, mixed,
    or unknown.

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

    def detect(self, image: np.ndarray) -> dict[str, Any]:
        """
        Classify the text region in *image*.

        Parameters
        ----------
        image : np.ndarray
            A BGR or grayscale crop of a single text region.

        Returns
        -------
        dict with keys ``text_type`` (str) and ``confidence`` (float).
        """
        if self._use_model and self._model is not None:
            return self._model_predict(image)
        return self._heuristic_detect(image)

    def detect_regions(
        self, regions: list[dict[str, Any]], page_image: np.ndarray
    ) -> list[dict[str, Any]]:
        """
        Run detection on a list of OCR region dicts, cropping from *page_image*.

        Each region dict is expected to have a ``bbox`` key: [x1, y1, x2, y2].
        The ``text_type`` and ``text_type_confidence`` keys are added in-place.

        Parameters
        ----------
        regions : list[dict]
        page_image : np.ndarray
            Full-page BGR image.

        Returns
        -------
        list[dict]
            The same list with added fields.
        """
        h, w = page_image.shape[:2]

        for region in regions:
            bbox = region.get("bbox", [0, 0, 0, 0])
            if len(bbox) != 4:
                region["text_type"] = TextType.UNKNOWN.value
                region["text_type_confidence"] = 0.0
                continue

            x1, y1, x2, y2 = (
                max(0, int(bbox[0])),
                max(0, int(bbox[1])),
                min(w, int(bbox[2])),
                min(h, int(bbox[3])),
            )

            if x2 <= x1 or y2 <= y1:
                region["text_type"] = TextType.UNKNOWN.value
                region["text_type_confidence"] = 0.0
                continue

            crop = page_image[y1:y2, x1:x2]
            result = self.detect(crop)
            region["text_type"] = result["text_type"]
            region["text_type_confidence"] = result["confidence"]

        return regions

    # ------------------------------------------------------------------ #
    # Model loading                                                        #
    # ------------------------------------------------------------------ #

    def _load_model_if_available(self) -> None:
        """Try to load a local sklearn classifier for text-type detection."""
        model_dir = Path(
            self._config.get("text_type_detection", {}).get(
                "model_path", "models/classifiers/text_type"
            )
        )
        model_file = model_dir / "classifier.pkl"

        if not model_file.exists():
            log.debug(
                "No text-type classifier found at '%s'. Using heuristic.", model_file
            )
            return

        try:
            import pickle
            with open(model_file, "rb") as fh:
                self._model = pickle.load(fh)
            self._use_model = True
            log.info("Loaded text-type classifier from '%s'.", model_file)
        except Exception as exc:
            log.warning("Failed to load text-type classifier: %s", exc)

    # ------------------------------------------------------------------ #
    # Heuristic detection                                                  #
    # ------------------------------------------------------------------ #

    def _heuristic_detect(self, image: np.ndarray) -> dict[str, Any]:
        """
        Image-based heuristic.

        Features
        --------
        * Stroke width transform variance  — printed text tends to have
          uniform stroke widths; handwriting varies more.
        * Local contrast (std dev of Laplacian) — handwriting usually shows
          less uniform contrast patterns than printed text.

        Returns a conservative estimate.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

        if gray.size < 100:
            return {"text_type": TextType.UNKNOWN.value, "confidence": 0.0}

        # Feature 1: stroke width variance
        swt_var = _stroke_width_variance(gray)

        # Feature 2: Laplacian std dev (texture roughness)
        lap_std = float(cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F).std())

        # Heuristic decision thresholds (tuned empirically)
        HIGH_VAR   = 4.0
        HIGH_LAP   = 30.0

        if swt_var > HIGH_VAR or lap_std > HIGH_LAP:
            return {"text_type": TextType.HANDWRITTEN.value, "confidence": 0.70}

        if swt_var < 1.5 and lap_std < 15.0:
            return {"text_type": TextType.PRINTED.value, "confidence": 0.75}

        return {"text_type": TextType.UNKNOWN.value, "confidence": 0.50}

    # ------------------------------------------------------------------ #
    # Model-based prediction                                               #
    # ------------------------------------------------------------------ #

    def _model_predict(self, image: np.ndarray) -> dict[str, Any]:
        """Use the loaded sklearn classifier."""
        features = _extract_features(image)
        X = np.array([features])

        label_idx = int(self._model.predict(X)[0])
        proba = self._model.predict_proba(X)[0]
        confidence = float(proba[label_idx])

        labels = [t.value for t in TextType]
        text_type = labels[label_idx] if label_idx < len(labels) else TextType.UNKNOWN.value

        return {"text_type": text_type, "confidence": confidence}


# ──────────────────────────────────────────────────────────────────────────────
# Feature extraction helpers (used by both heuristic and ML model training)
# ──────────────────────────────────────────────────────────────────────────────

def _stroke_width_variance(gray: np.ndarray) -> float:
    """
    Approximate stroke-width variance using distance transform on binarised image.
    Higher variance → more irregular strokes (handwriting).
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    nonzero = dist[dist > 0]
    if nonzero.size == 0:
        return 0.0
    return float(np.var(nonzero))


def _extract_features(image: np.ndarray) -> list[float]:
    """
    Extract a fixed-length feature vector from a text region image.
    Used when training and running the ML classifier.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    resized = cv2.resize(gray, (64, 32))

    swt_var = _stroke_width_variance(resized)
    lap_std = float(cv2.Laplacian(resized.astype(np.float32), cv2.CV_32F).std())
    mean_px = float(resized.mean())
    std_px = float(resized.std())

    return [swt_var, lap_std, mean_px, std_px]
