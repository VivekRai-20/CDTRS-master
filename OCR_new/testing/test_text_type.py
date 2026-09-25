"""
testing/test_text_type.py
--------------------------
Unit tests for the text-type detector.
"""

from __future__ import annotations

import numpy as np
import unittest

from ocr.text_type_detector import (
    FEATURE_NAMES, FEATURE_VERSION, TextType, TextTypeDetector, _extract_features, extract_features,
)

from testing import TempDirTestCase


class TestTextTypeDetector(unittest.TestCase):
    def setUp(self):
        self.detector = TextTypeDetector(config={})

    def _make_image(self, h=64, w=128, value=200):
        return np.full((h, w, 3), value, dtype=np.uint8)

    def test_detect_returns_dict(self):
        img = self._make_image()
        result = self.detector.detect(img)
        assert isinstance(result, dict)
        assert "text_type" in result
        assert "confidence" in result

    def test_detect_valid_text_type(self):
        img = self._make_image()
        result = self.detector.detect(img)
        valid = {t.value for t in TextType}
        assert result["text_type"] in valid

    def test_detect_confidence_in_range(self):
        img = self._make_image()
        result = self.detector.detect(img)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_detect_tiny_image_returns_unknown(self):
        img = np.zeros((5, 5, 3), dtype=np.uint8)
        result = self.detector.detect(img)
        assert result["text_type"] == TextType.UNKNOWN.value

    def test_detect_regions_adds_text_type_field(self):
        img = self._make_image(h=300, w=400)
        regions = [
            {"text": "Hello", "bbox": [10, 10, 200, 50], "page": 1}
        ]
        updated = self.detector.detect_regions(regions, img)
        assert "text_type" in updated[0]
        assert "text_type_confidence" in updated[0]

    def test_extract_features_returns_list(self):
        img = self._printed_line()
        features = _extract_features(img)
        assert isinstance(features, list)
        assert len(features) == len(FEATURE_NAMES)

    def test_extract_features_blank_image(self):
        features = extract_features(self._make_image())
        assert features is None or features[FEATURE_NAMES.index("cc_count")] == 0

    @staticmethod
    def _printed_line(text="Ministry of Finance, Department of Expenditure"):
        import cv2
        img = np.full((48, 900, 3), 255, dtype=np.uint8)
        cv2.putText(img, text, (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
        return img

    def test_printed_line_is_not_handwritten(self):
        result = self.detector.detect(self._printed_line(), ocr_confidence=0.99)
        assert result["text_type"] != TextType.HANDWRITTEN.value

    def test_too_few_glyphs_is_unknown(self):
        result = self.detector.detect(self._printed_line("A"), ocr_confidence=0.99)
        assert result["text_type"] == TextType.UNKNOWN.value


class TestTrainedClassifier(TempDirTestCase):
    """A classifier from fineTune/training/train.py --task text_type is used,
    and one with outdated features is ignored."""

    def _write_bundle(self, feature_version):
        import pickle
        from sklearn.ensemble import RandomForestClassifier
        rng = np.random.default_rng(0)
        X = rng.random((40, len(FEATURE_NAMES)))
        y = np.array([0, 1] * 20)
        model = RandomForestClassifier(n_estimators=5, random_state=0).fit(X, y)
        folder = self.tmp_path / "text_type"
        folder.mkdir()
        with open(folder / "classifier.pkl", "wb") as fh:
            pickle.dump({"model": model, "features": FEATURE_NAMES, "labels": ["PRINTED", "HANDWRITTEN"],
                         "feature_version": feature_version}, fh)
        return {"text_type_detection": {"model_path": str(folder)}}

    def test_current_bundle_is_used(self):
        detector = TextTypeDetector(self._write_bundle(FEATURE_VERSION))
        assert detector.source == "trained classifier"
        result = detector.detect(TestTextTypeDetector._printed_line(), 0.95)
        assert result["text_type"] in {t.value for t in TextType}

    def test_outdated_bundle_is_ignored(self):
        detector = TextTypeDetector(self._write_bundle(FEATURE_VERSION - 1))
        assert detector.source == "built-in model"
