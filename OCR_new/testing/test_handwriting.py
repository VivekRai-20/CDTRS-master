"""
testing/test_handwriting.py
-----------------------------
Unit tests for the handwriting OCR engine.
(Tests that don't require the actual model to be present.)
"""

from __future__ import annotations

import numpy as np
import unittest

from ocr.handwriting_engine import HandwritingEngine


class TestHandwritingEngine(unittest.TestCase):
    def test_engine_name(self):
        engine = HandwritingEngine()
        assert engine.ENGINE_NAME == "HandwritingEngine"

    def test_recognize_without_init_returns_empty(self):
        """Engine should return [] gracefully if not initialized."""
        engine = HandwritingEngine()
        img = np.zeros((64, 200, 3), dtype=np.uint8)
        result = engine.recognize(img, page=1)
        assert result == []

    def test_initialize_missing_model_raises(self):
        """Should raise FileNotFoundError with clear message if model is missing."""
        engine = HandwritingEngine()
        config = {
            "handwriting": {
                "enabled": True,
                "model_path": "/nonexistent/path/that/does/not/exist",
            }
        }
        with self.assertRaises(FileNotFoundError) as exc_info:
            engine.initialize(config)
        assert "Automatic downloads are disabled" in str(exc_info.exception)

    def test_initialize_disabled_skips_loading(self):
        """If handwriting is disabled in config, no error should be raised."""
        engine = HandwritingEngine()
        config = {"handwriting": {"enabled": False}}
        engine.initialize(config)  # Should not raise
        assert not engine._initialized

    def test_bbox_to_list_polygon(self):
        """Test inherited bbox normalisation helper."""
        from ocr.base_engine import BaseOCREngine
        polygon = [[10, 20], [100, 20], [100, 50], [10, 50]]
        result = BaseOCREngine.bbox_to_list(polygon)
        assert result == [10, 20, 100, 50]

    def test_bbox_to_list_flat(self):
        from ocr.base_engine import BaseOCREngine
        flat = [10, 20, 100, 50]
        result = BaseOCREngine.bbox_to_list(flat)
        assert result == flat
