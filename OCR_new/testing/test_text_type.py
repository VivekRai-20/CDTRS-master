"""
testing/test_text_type.py
--------------------------
Unit tests for the text-type detector.
"""

from __future__ import annotations

import numpy as np
import pytest

from ocr.text_type_detector import TextTypeDetector, TextType, _extract_features


class TestTextTypeDetector:
    def setup_method(self):
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
        img = self._make_image()
        features = _extract_features(img)
        assert isinstance(features, list)
        assert len(features) == 4
