"""
ocr/text_type_detector.py
--------------------------
Classify each text line as PRINTED, HANDWRITTEN or UNKNOWN.

How it decides
--------------
1.  A classifier you trained on your own labelled lines
    (``fineTune/training/train.py --task text_type``) is used when
    ``models/classifiers/text_type/classifier.pkl`` exists.
2.  Otherwise a built-in model is used: a small logistic regression over
    shape measurements of the line (see ``extract_features``), fitted on
    printed letters, forms and scans plus a handwritten notebook.

Both look at the same measurements:

* how uniform the glyph heights are and whether glyphs share one baseline
  (print: a few exact sizes on one baseline; handwriting: sizes vary),
* how uniform the stroke width is and how much of each glyph box is ink,
* how much the stroke slant varies, and PaddleOCR's own reading confidence
  (print is usually read with more confidence).

The detector is deliberately cautious: when it is unsure it answers UNKNOWN,
and lines with fewer than three glyphs are always UNKNOWN.

Output of ``detect``::

    {"text_type": "PRINTED" | "HANDWRITTEN" | "UNKNOWN", "confidence": 0.0-1.0}
"""

from __future__ import annotations

import math
import pickle
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)

_OCR_ROOT = Path(__file__).resolve().parents[1]


class TextType(str, Enum):
    PRINTED     = "PRINTED"
    HANDWRITTEN = "HANDWRITTEN"
    MIXED       = "MIXED"
    UNKNOWN     = "UNKNOWN"


# ──────────────────────────────────────────────────────────────────────────────
# Features
# ──────────────────────────────────────────────────────────────────────────────

FEATURE_VERSION = 2
FEATURE_NAMES = [
    "ocr_confidence",    # PaddleOCR recognition confidence of the line
    "aspect",            # crop width / height
    "ink_density",       # share of ink pixels
    "cc_per_unit",       # glyph components per line-height of width
    "cc_height_cv",      # variation of glyph heights
    "cc_bottom_dev",     # spread of glyph bottoms (baseline)
    "cc_top_dev",        # spread of glyph tops
    "cc_wh_median",      # typical glyph width / height
    "cc_extent_median",  # typical ink share of a glyph's box
    "stroke_width",      # stroke width / line height
    "stroke_cv",         # variation of stroke width
    "axis_aligned",      # share of edges that are horizontal / vertical
    "orient_entropy",    # spread of edge directions
    "slant_std",         # variation of the slant of near-vertical strokes
    "core_band_ratio",   # height of the band holding the middle 50% of ink
    "edge_sharpness",    # typical edge strength / contrast
    "height_nn",         # how close each glyph height is to another glyph's
    "baseline_share",    # share of glyphs sitting on the most common baseline
    "top_share",         # share of glyphs with the most common top
    "cc_count",          # number of glyph components
]
_LINE_HEIGHT = 64


def _gray(image: np.ndarray) -> np.ndarray:
    image = np.asarray(image)
    if image.ndim == 3:
        return cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    return image.copy()


def extract_features(image: np.ndarray, ocr_confidence: Optional[float] = None) -> Optional[np.ndarray]:
    """Shape measurements of one text-line image (BGR or gray), in the order
    of FEATURE_NAMES.  Returns None for images too small to measure."""
    H = _LINE_HEIGHT
    g = _gray(image)
    h0, w0 = g.shape[:2]
    if h0 < 6 or w0 < 6:
        return None
    scale = H / h0
    w = max(16, int(round(w0 * scale)))
    g = cv2.resize(g, (w, H), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)

    # Ink = dark on light; drop long horizontal rules (underlines, ruled paper).
    _, binary = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    rules = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 3), 1)))
    binary = cv2.subtract(binary, rules)
    ink = binary > 0
    density = float(ink.mean())

    _, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    comps = [s for s in stats[1:]
             if s[cv2.CC_STAT_AREA] >= 0.004 * H * H and s[cv2.CC_STAT_HEIGHT] >= 0.15 * H]
    units = max(1.0, w / H)
    height_cv = bottom_dev = top_dev = wh = extent = cc_per_unit = 0.0
    height_nn, baseline_share, top_share = 0.1, 0.5, 0.5
    if comps:
        hts = np.array([c[cv2.CC_STAT_HEIGHT] for c in comps], float)
        wds = np.array([c[cv2.CC_STAT_WIDTH] for c in comps], float)
        tops = np.array([c[cv2.CC_STAT_TOP] for c in comps], float)
        bottoms = tops + hts
        areas = np.array([c[cv2.CC_STAT_AREA] for c in comps], float)
        med_h = float(np.median(hts)) or 1.0
        height_cv = float(hts.std() / (hts.mean() or 1.0))
        bottom_dev = float(np.median(np.abs(bottoms - np.median(bottoms))) / med_h)
        top_dev = float(np.median(np.abs(tops - np.median(tops))) / med_h)
        wh = float(np.median(wds / np.maximum(hts, 1)))
        extent = float(np.median(areas / np.maximum(wds * hts, 1)))
        cc_per_unit = len(comps) / units
        if len(hts) >= 3:
            diffs = np.abs(hts[:, None] - hts[None, :]) + np.eye(len(hts)) * 1e9
            height_nn = float(np.median(diffs.min(axis=1)) / med_h)
            tol = 0.035 * H
            values, counts = np.unique(np.round(bottoms / tol), return_counts=True)
            baseline_share = float(np.mean(np.abs(bottoms - values[np.argmax(counts)] * tol) <= tol))
            values, counts = np.unique(np.round(tops / tol), return_counts=True)
            top_share = float(np.mean(np.abs(tops - values[np.argmax(counts)] * tol) <= tol))

    # Stroke width, measured on the ridge of the distance transform.
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    ridge = (dist > 0) & (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8)))
    values = dist[ridge]
    stroke_width = float(values.mean() * 2 / H) if values.size else 0.0
    stroke_cv = float(values.std() / (values.mean() or 1.0)) if values.size else 0.0

    # Edge directions.
    gf = g.astype(np.float32)
    gx = cv2.Sobel(gf, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gf, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    strong = mag > max(20.0, float(np.percentile(mag, 90)) * 0.3)
    entropy = axis = slant = 0.0
    if strong.sum() > 10:
        ang = (np.degrees(np.arctan2(gy[strong], gx[strong])) + 180.0) % 180.0
        weights = mag[strong]
        hist, _ = np.histogram(ang, bins=18, range=(0, 180), weights=weights)
        p = hist / (hist.sum() or 1.0)
        entropy = float(-(p[p > 0] * np.log(p[p > 0])).sum() / math.log(18))

        def near(a: float) -> np.ndarray:
            return np.minimum(np.abs(ang - a), 180 - np.abs(ang - a)) <= 7.5

        axis = float(weights[near(0) | near(90)].sum() / weights.sum())
        vertical = np.minimum(ang, 180 - ang) <= 35
        if vertical.sum() > 5:
            a = ang[vertical]
            slant = float(np.std(np.where(a > 90, a - 180, a)))

    rows = ink.sum(axis=1).astype(float)
    core = 0.0
    if rows.sum() > 0:
        cum = np.cumsum(rows) / rows.sum()
        core = float((np.searchsorted(cum, 0.75) - np.searchsorted(cum, 0.25) + 1) / H)
    edges = mag[strong]
    contrast = float(np.percentile(g, 95) - np.percentile(g, 5)) or 1.0
    sharpness = float(np.median(edges) / contrast) if edges.size else 0.0
    confidence = float(ocr_confidence) if ocr_confidence is not None else 0.9

    return np.array([
        confidence, min(w0 / max(h0, 1), 60.0), density, cc_per_unit, height_cv, bottom_dev,
        top_dev, wh, extent, stroke_width, stroke_cv, axis, entropy, slant / 30.0, core,
        sharpness, height_nn, baseline_share, top_share, float(len(comps)),
    ], dtype=np.float32)


def _extract_features(image: np.ndarray) -> list[float]:
    """Backward-compatible alias (list of floats, no OCR confidence)."""
    features = extract_features(image)
    return [] if features is None else [float(v) for v in features]


# ──────────────────────────────────────────────────────────────────────────────
# Built-in model (used until you train your own - see fineTune/README.md)
# ──────────────────────────────────────────────────────────────────────────────

# Logistic regression on standardised features, fitted on ~1,900 lines:
# printed letters, notices and forms (scanned and digital, 60+ fonts) and a
# handwritten notebook.  P(handwritten) = sigmoid(b + sum(w * (x - mean) / scale)).
_BUILTIN = {
    "features": ["ocr_confidence", "cc_height_cv", "cc_top_dev", "cc_bottom_dev", "cc_extent_median",
                 "stroke_cv", "slant_std", "core_band_ratio", "cc_per_unit", "height_nn",
                 "baseline_share", "top_share"],
    "mean":  [0.8964, 0.198, 0.1183, 0.0822, 0.4524, 0.2823, 0.5488, 0.2798, 2.0314, 0.0362, 0.6828, 0.5433],
    "scale": [0.1655, 0.1287, 0.1628, 0.1562, 0.1131, 0.1401, 0.0571, 0.0717, 0.6621, 0.0708, 0.2819, 0.2328],
    "coef":  [-0.884, 1.37, -0.129, -0.402, -1.188, 1.187, 0.78, 1.109, -0.401, 2.901, -0.317, -0.825],
    "intercept": -1.582,
}
_HANDWRITTEN_AT = 0.70   # P(handwritten) at or above -> HANDWRITTEN
_PRINTED_AT = 0.35       # P(handwritten) at or below -> PRINTED
_MIN_GLYPHS = 3


def _builtin_probability(features: np.ndarray) -> float:
    idx = [FEATURE_NAMES.index(name) for name in _BUILTIN["features"]]
    x = (features[idx] - np.array(_BUILTIN["mean"])) / np.array(_BUILTIN["scale"])
    z = float(np.dot(np.array(_BUILTIN["coef"]), x) + _BUILTIN["intercept"])
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


def default_model_path(config: Optional[dict] = None) -> Path:
    rel = ((config or {}).get("text_type_detection") or {}).get("model_path", "models/classifiers/text_type")
    path = Path(rel)
    return (path if path.is_absolute() else _OCR_ROOT / path) / "classifier.pkl"


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

class TextTypeDetector:
    """Detects whether a text-line image is printed or handwritten."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._model = None           # trained classifier (sklearn estimator)
        self._model_features = None  # feature names the classifier expects
        self._model_labels = None    # class index -> TextType value
        self._use_model = False
        self._load_model_if_available()

    @property
    def source(self) -> str:
        return "trained classifier" if self._use_model else "built-in model"

    def detect(self, image: np.ndarray, ocr_confidence: Optional[float] = None) -> dict[str, Any]:
        """Classify one text-line image."""
        features = extract_features(image, ocr_confidence)
        if features is None or features[FEATURE_NAMES.index("cc_count")] < _MIN_GLYPHS:
            return {"text_type": TextType.UNKNOWN.value, "confidence": 0.0}
        if self._use_model and self._model is not None:
            try:
                return self._model_predict(features)
            except Exception as exc:  # e.g. a classifier from an older feature set
                log.warning("Text-type classifier failed (%s); using the built-in model.", exc)
                self._use_model = False
        p_hw = _builtin_probability(features)
        return self._decide(p_hw)

    @staticmethod
    def _decide(p_hw: float) -> dict[str, Any]:
        if p_hw >= _HANDWRITTEN_AT:
            return {"text_type": TextType.HANDWRITTEN.value, "confidence": round(p_hw, 4)}
        if p_hw <= _PRINTED_AT:
            return {"text_type": TextType.PRINTED.value, "confidence": round(1.0 - p_hw, 4)}
        return {"text_type": TextType.UNKNOWN.value, "confidence": round(max(p_hw, 1.0 - p_hw), 4)}

    def detect_regions(self, regions: list[dict[str, Any]], page_image: np.ndarray) -> list[dict[str, Any]]:
        """Add ``text_type`` / ``text_type_confidence`` to each OCR region,
        cropping its ``bbox`` [x1, y1, x2, y2] from *page_image*."""
        h, w = page_image.shape[:2]
        for region in regions:
            bbox = region.get("bbox", [0, 0, 0, 0])
            if len(bbox) != 4:
                region["text_type"] = TextType.UNKNOWN.value
                region["text_type_confidence"] = 0.0
                continue
            x1, y1 = max(0, int(bbox[0])), max(0, int(bbox[1]))
            x2, y2 = min(w, int(bbox[2])), min(h, int(bbox[3]))
            if x2 <= x1 or y2 <= y1:
                region["text_type"] = TextType.UNKNOWN.value
                region["text_type_confidence"] = 0.0
                continue
            result = self.detect(page_image[y1:y2, x1:x2], region.get("confidence"))
            region["text_type"] = result["text_type"]
            region["text_type_confidence"] = result["confidence"]
        return regions

    # ------------------------------------------------------------------ #
    # Trained classifier                                                   #
    # ------------------------------------------------------------------ #

    def _load_model_if_available(self) -> None:
        model_file = default_model_path(self._config)
        if not model_file.exists():
            log.debug("No trained text-type classifier at '%s'; using the built-in model.", model_file)
            return
        try:
            with open(model_file, "rb") as fh:
                bundle = pickle.load(fh)
        except Exception as exc:
            log.warning("Could not load the text-type classifier %s: %s", model_file, exc)
            return
        if isinstance(bundle, dict) and "model" in bundle:
            if bundle.get("feature_version") != FEATURE_VERSION:
                log.warning("Text-type classifier %s was trained with older features; "
                            "retrain it (fineTune/training/train.py --task text_type).", model_file)
                return
            self._model = bundle["model"]
            self._model_features = bundle.get("features") or FEATURE_NAMES
            self._model_labels = bundle.get("labels") or [TextType.PRINTED.value, TextType.HANDWRITTEN.value]
        else:
            log.warning("Text-type classifier %s has an unknown format; retrain it.", model_file)
            return
        self._use_model = True
        log.info("Loaded text-type classifier from '%s'.", model_file)

    def _model_predict(self, features: np.ndarray) -> dict[str, Any]:
        idx = [FEATURE_NAMES.index(name) for name in self._model_features]
        proba = self._model.predict_proba(features[idx].reshape(1, -1))[0]
        classes = list(getattr(self._model, "classes_", range(len(proba))))
        by_label = {self._model_labels[int(c)]: float(p) for c, p in zip(classes, proba)}
        return self._decide(by_label.get(TextType.HANDWRITTEN.value, 0.0))
