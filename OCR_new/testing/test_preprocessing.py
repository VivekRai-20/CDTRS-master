"""
testing/test_preprocessing.py
-------------------------------
Unit tests for preprocessing modules: deskew, denoise, threshold, orientation.
"""

from __future__ import annotations

import numpy as np
import unittest

from preprocessing.deskew import deskew
from preprocessing.denoise import denoise
from preprocessing.threshold import threshold


def _white_image(h=100, w=200):
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _noisy_image(h=100, w=200):
    img = np.full((h, w, 3), 200, dtype=np.uint8)
    rng = np.random.default_rng(42)
    noise = rng.integers(-30, 30, img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


class TestDeskew(unittest.TestCase):
    def test_deskew_returns_ndarray(self):
        img = _white_image()
        result = deskew(img)
        assert isinstance(result, np.ndarray)

    def test_deskew_no_skew_returns_similar_shape(self):
        img = _white_image()
        result = deskew(img)
        # Shape may vary slightly due to canvas expansion
        assert result.ndim == img.ndim

    def test_deskew_preserves_dtype(self):
        img = _white_image()
        result = deskew(img)
        assert result.dtype == img.dtype


class TestDenoise(unittest.TestCase):
    def test_denoise_median_returns_ndarray(self):
        img = _noisy_image()
        config = {"preprocessing": {"denoise_method": "median"}}
        result = denoise(img, config)
        assert isinstance(result, np.ndarray)
        assert result.shape == img.shape

    def test_denoise_gaussian_returns_ndarray(self):
        img = _noisy_image()
        config = {"preprocessing": {"denoise_method": "gaussian"}}
        result = denoise(img, config)
        assert result.shape == img.shape

    def test_denoise_nlm_returns_ndarray(self):
        img = _noisy_image()
        config = {"preprocessing": {"denoise_method": "nlm"}}
        result = denoise(img, config)
        assert result.shape == img.shape

    def test_denoise_invalid_method_falls_back(self):
        img = _noisy_image()
        config = {"preprocessing": {"denoise_method": "unknown_method"}}
        result = denoise(img, config)
        assert isinstance(result, np.ndarray)


class TestThreshold(unittest.TestCase):
    def test_threshold_otsu(self):
        img = _white_image()
        config = {"preprocessing": {"threshold_method": "otsu"}}
        result = threshold(img, config)
        assert result.ndim == 2  # single channel
        assert result.dtype == np.uint8

    def test_threshold_adaptive(self):
        img = _white_image()
        config = {"preprocessing": {"threshold_method": "adaptive"}}
        result = threshold(img, config)
        assert result.ndim == 2

    def test_threshold_simple(self):
        img = _white_image()
        config = {"preprocessing": {"threshold_method": "simple"}}
        result = threshold(img, config)
        assert result.ndim == 2

    def test_threshold_no_config(self):
        img = _white_image()
        result = threshold(img)
        assert isinstance(result, np.ndarray)
