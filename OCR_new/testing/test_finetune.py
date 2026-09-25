"""
testing/test_finetune.py
------------------------
Tests for the fine-tuning helpers (fineTune/common.py) and the line
preparation shared by training and recognition.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fineTune"))

import common  # noqa: E402  (fineTune/common.py)
from ocr.handwriting_engine import prepare_line_image, resolve_model_dir  # noqa: E402
from testing import TempDirTestCase  # noqa: E402


class TestLabels(TempDirTestCase):
    def test_roundtrip_keeps_unicode_and_columns(self):
        path = self.tmp_path / "labels.csv"
        rows = [{"image": "a.png", "text": "Dr. Sharmā – 5,000", "type": "HANDWRITTEN", "split": "train"}]
        common.write_labels(rows, path)
        back = common.read_labels(path)
        assert back[0]["text"] == "Dr. Sharmā – 5,000"
        assert set(common.COLUMNS) <= set(back[0])

    def test_missing_file_gives_no_rows(self):
        assert common.read_labels(self.tmp_path / "none.csv") == []

    def test_is_labelled(self):
        assert common.is_labelled({"type": "HANDWRITTEN", "text": "abc"})
        assert common.is_labelled({"type": "SKIP", "text": ""})
        assert not common.is_labelled({"type": "HANDWRITTEN", "text": " "})
        assert not common.is_labelled({"type": "", "text": "abc"})

    def test_labelled_rows_filters_split_and_type(self):
        rows = [{"type": "HANDWRITTEN", "text": "a", "split": "train"},
                {"type": "PRINTED", "text": "b", "split": "train"},
                {"type": "HANDWRITTEN", "text": "c", "split": "test"},
                {"type": "HANDWRITTEN", "text": "", "split": "train"}]
        assert [r["text"] for r in common.labelled_rows(rows, ["HANDWRITTEN"], "train")] == ["a"]
        assert len(common.labelled_rows(rows, ["HANDWRITTEN", "PRINTED"], None)) == 3


class TestSplitsAndScores(unittest.TestCase):
    def test_split_is_stable_and_balanced(self):
        names = [f"line_{i}.png" for i in range(2000)]
        splits = [common.assign_split(n) for n in names]
        assert splits == [common.assign_split(n) for n in names]
        share = {s: splits.count(s) / len(splits) for s in ("train", "val", "test")}
        assert 0.07 < share["test"] < 0.13 and 0.07 < share["val"] < 0.13

    def test_error_rates(self):
        assert common.error_rates(["hello world"], ["hello world"])["cer"] == 0.0
        scores = common.error_rates(["hello world"], ["hallo world"])
        assert abs(scores["cer"] - 1 / 11) < 1e-3
        assert scores["wer"] == 0.5

    def test_next_version(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assert common.next_version(root) == "v1"
            (root / "v1").mkdir()
            (root / "v3").mkdir()
            assert common.next_version(root) == "v2"


class TestLinePreparation(unittest.TestCase):
    def test_prepare_line_image_returns_rgb(self):
        img = np.full((40, 300, 3), 255, dtype=np.uint8)
        img[15:25, 20:280] = 0
        out = prepare_line_image(img)
        assert out.ndim == 3 and out.shape[2] == 3 and out.dtype == np.uint8

    def test_no_active_model_is_none(self):
        cfg = {"handwriting": {"model_path": "/nonexistent/handwriting"}}
        assert resolve_model_dir(cfg) is None


if __name__ == "__main__":
    unittest.main()
