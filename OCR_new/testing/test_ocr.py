"""
testing/test_ocr.py
--------------------
Unit and integration tests for the OCR pipeline.

These tests REQUIRE the PaddleOCR models to be installed in models/paddleocr/.
Run setup_models.py first if models are not yet downloaded.

Run with:
    python -m unittest testing.test_ocr -v
or:
    python testing/test_ocr.py
"""

from __future__ import annotations

import sys
import os
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import yaml

from utils.logger import setup_root_logger, get_logger
from utils.offline_checker import check_model_dirs


def _load_config() -> dict:
    with open(_ROOT / "config" / "config.yaml", "r") as fh:
        return yaml.safe_load(fh) or {}


_CONFIG = _load_config()
setup_root_logger(_CONFIG.get("logging", {}))
log = get_logger(__name__)


# =========================================================================== #
# Skip guard — skip all OCR tests if models are missing                       #
# =========================================================================== #

_models_ok, _ = check_model_dirs(_CONFIG)
_SKIP_OCR = not _models_ok
_SKIP_REASON = (
    "PaddleOCR model directories are missing or empty. "
    "Run 'python setup_models.py' first."
)


def _skip_if_no_models(test_func):
    """Decorator: skip if OCR models are not available."""
    import functools
    @functools.wraps(test_func)
    def wrapper(*args, **kwargs):
        if _SKIP_OCR:
            raise unittest.SkipTest(_SKIP_REASON)
        return test_func(*args, **kwargs)
    return wrapper


# =========================================================================== #
# Helpers                                                                      #
# =========================================================================== #

def _make_white_image(
    width: int = 400, height: int = 100, text: str = "Hello World"
) -> np.ndarray:
    """
    Create a minimal synthetic image with text for basic OCR validation.
    Requires OpenCV + Pillow (both are runtime deps anyway).
    """
    import cv2
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), text, fill=(0, 0, 0))
    arr = np.array(img, dtype=np.uint8)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


# =========================================================================== #
# Tests: Offline checker                                                       #
# =========================================================================== #

class TestOfflineChecker(unittest.TestCase):
    """Offline check utility tests — no model files required."""

    def test_check_offline_mode_flag(self):
        from utils.offline_checker import check_offline_mode
        cfg_on  = {"offline_mode": True}
        # Should not raise
        check_offline_mode(cfg_on)

    def test_patterns_file_found(self):
        from utils.offline_checker import check_patterns_file
        result = check_patterns_file(_CONFIG)
        self.assertTrue(result)

    def test_model_dirs_returns_tuple(self):
        ok, missing = check_model_dirs(_CONFIG)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(missing, list)


# =========================================================================== #
# Tests: Preprocessing                                                         #
# =========================================================================== #

class TestPreprocessor(unittest.TestCase):
    """Image preprocessing tests — no models required."""

    def test_preprocess_returns_ndarray(self):
        from preprocessing.image_preprocessor import preprocess
        img    = _make_white_image()
        result = preprocess(img, _CONFIG)
        self.assertIsInstance(result, np.ndarray)

    def test_preprocess_output_is_3channel(self):
        """PaddleOCR expects 3-channel BGR input."""
        from preprocessing.image_preprocessor import preprocess
        img    = _make_white_image()
        result = preprocess(img, _CONFIG)
        self.assertEqual(len(result.shape), 3)
        self.assertEqual(result.shape[2], 3)

    def test_preprocess_disabled(self):
        """When preprocessing is disabled, image should pass through unchanged (copy)."""
        from preprocessing.image_preprocessor import preprocess
        cfg = dict(_CONFIG)
        cfg["preprocessing"] = {"enabled": False}
        img    = _make_white_image()
        result = preprocess(img, cfg)
        self.assertIsInstance(result, np.ndarray)

    def test_preprocess_does_not_modify_original(self):
        from preprocessing.image_preprocessor import preprocess
        img      = _make_white_image()
        original = img.copy()
        preprocess(img, _CONFIG)
        np.testing.assert_array_equal(img, original, "Original image must not be modified")


# =========================================================================== #
# Tests: File detector                                                         #
# =========================================================================== #

class TestFileDetector(unittest.TestCase):
    """File type detection — no models required."""

    def _tmp_file(self, suffix: str) -> Path:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self._files_to_clean = getattr(self, "_files_to_clean", [])
        self._files_to_clean.append(path)
        return Path(path)

    def tearDown(self):
        for f in getattr(self, "_files_to_clean", []):
            try:
                os.unlink(f)
            except OSError:
                pass

    def test_detect_jpg(self):
        from document.file_detector import detect, DocumentType
        p = self._tmp_file(".jpg")
        p.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        self.assertEqual(detect(p), DocumentType.IMAGE)

    def test_detect_png_by_extension(self):
        from document.file_detector import detect, DocumentType
        p = self._tmp_file(".png")
        p.write_bytes(b"\x89PNG" + b"\x00" * 10)
        self.assertEqual(detect(p), DocumentType.IMAGE)

    def test_detect_pdf(self):
        from document.file_detector import detect, DocumentType
        p = self._tmp_file(".pdf")
        p.write_bytes(b"%PDF-1.4\n")
        self.assertEqual(detect(p), DocumentType.PDF)

    def test_missing_file_raises(self):
        from document.file_detector import detect
        with self.assertRaises(FileNotFoundError):
            detect("/nonexistent/path/file.jpg")


# =========================================================================== #
# Tests: OCR Engine (requires models)                                         #
# =========================================================================== #

class TestPaddleEngine(unittest.TestCase):

    @classmethod
    @_skip_if_no_models
    def setUpClass(cls):
        from ocr.paddle_engine import PaddleEngine
        cls.engine = PaddleEngine()
        cls.engine.initialize(_CONFIG)

    @_skip_if_no_models
    def test_engine_is_ready(self):
        self.assertTrue(self.engine.is_ready)

    @_skip_if_no_models
    def test_recognize_returns_list(self):
        img    = _make_white_image(text="Test OCR")
        result = self.engine.recognize(img, page=1)
        self.assertIsInstance(result, list)

    @_skip_if_no_models
    def test_recognize_result_schema(self):
        img    = _make_white_image(text="Subject: Test")
        result = self.engine.recognize(img, page=1)
        for region in result:
            self.assertIn("text",       region)
            self.assertIn("confidence", region)
            self.assertIn("bbox",       region)
            self.assertIn("page",       region)
            self.assertIsInstance(region["text"],       str)
            self.assertIsInstance(region["confidence"], float)
            self.assertIsInstance(region["bbox"],       list)
            self.assertEqual(len(region["bbox"]),       4)
            self.assertEqual(region["page"],            1)

    @_skip_if_no_models
    def test_recognize_confidence_in_range(self):
        img    = _make_white_image(text="Hello World")
        result = self.engine.recognize(img, page=1)
        for region in result:
            self.assertGreaterEqual(region["confidence"], 0.0)
            self.assertLessEqual(region["confidence"],    1.0)

    @_skip_if_no_models
    def test_recognize_empty_image_no_crash(self):
        """Completely blank image should not raise — may return empty list."""
        import cv2
        blank  = np.full((100, 400, 3), 255, dtype=np.uint8)
        result = self.engine.recognize(blank, page=1)
        self.assertIsInstance(result, list)


# =========================================================================== #
# Tests: OCR Pipeline (requires models)                                       #
# =========================================================================== #

class TestOCRPipeline(unittest.TestCase):

    @classmethod
    @_skip_if_no_models
    def setUpClass(cls):
        from ocr.paddle_engine import PaddleEngine
        from ocr.ocr_pipeline import OCRPipeline

        engine = PaddleEngine()
        engine.initialize(_CONFIG)
        cls.pipeline = OCRPipeline(engine, _CONFIG)

    def _write_temp_image(self, text: str) -> Path:
        """Write a synthetic image to a temp PNG and return its path."""
        from PIL import Image, ImageDraw
        img  = Image.new("RGB", (500, 120), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((10, 40), text, fill=(0, 0, 0))
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img.save(path)
        self._temp_files = getattr(self, "_temp_files", [])
        self._temp_files.append(path)
        return Path(path)

    def tearDown(self):
        for f in getattr(self, "_temp_files", []):
            try:
                os.unlink(f)
            except OSError:
                pass

    @_skip_if_no_models
    def test_pipeline_result_schema(self):
        img_path = self._write_temp_image("Name: Alice Roll No: 99")
        result   = self.pipeline.process(img_path)

        self.assertIn("file",      result)
        self.assertIn("doc_type",  result)
        self.assertIn("pages",     result)
        self.assertIn("regions",   result)
        self.assertIn("full_text", result)
        self.assertIn("elapsed_s", result)

    @_skip_if_no_models
    def test_pipeline_doc_type_is_image(self):
        img_path = self._write_temp_image("Test")
        result   = self.pipeline.process(img_path)
        self.assertEqual(result["doc_type"], "IMAGE")

    @_skip_if_no_models
    def test_pipeline_pages_at_least_one(self):
        img_path = self._write_temp_image("Sample text")
        result   = self.pipeline.process(img_path)
        self.assertGreaterEqual(result["pages"], 1)

    @_skip_if_no_models
    def test_pipeline_full_text_is_string(self):
        img_path = self._write_temp_image("Hello")
        result   = self.pipeline.process(img_path)
        self.assertIsInstance(result["full_text"], str)


# =========================================================================== #
# Standalone runner                                                            #
# =========================================================================== #

if __name__ == "__main__":
    if _SKIP_OCR:
        print(f"\n[NOTICE] OCR tests will be SKIPPED: {_SKIP_REASON}\n")
    unittest.main(verbosity=2)
