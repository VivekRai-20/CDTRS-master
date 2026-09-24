"""
testing/test_patterns.py
-------------------------
Unit tests for the regex pattern extraction system.

These tests do NOT require PaddleOCR or any model files.
They run purely on text and regex logic.

Run with:
    python -m pytest testing/test_patterns.py -v
or:
    python testing/test_patterns.py
"""

from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from extraction.pattern_manager import PatternManager
from extraction.regex_engine import RegexEngine


# =========================================================================== #
# Sample OCR text fixtures                                                     #
# =========================================================================== #

SAMPLE_TEXT_FULL = """\
Subject: Data Mining and Data Warehousing
Title: Association Rule Mining
Name: Vivek Rai
Roll No: 42
Date: 18/08/2026
Semester: IV
Department: Computer Science
"""

SAMPLE_TEXT_VARIATIONS = """\
Sub : Machine Learning
Topic : Neural Networks
Student Name : Alice Johnson
Enrollment No. : CS2024001
Date: 01-01-2025
Sem : VI
Dept. : Information Technology
"""

SAMPLE_TEXT_NOISY_OCR = """\
Subj ect :  Data  Structures
Titl e :   Sorting  Algorithms
Name :  Bob  Smith
Roll  No :  101
Date:18/06/2024
"""

SAMPLE_TEXT_EMPTY = ""

SAMPLE_TEXT_NO_MATCHES = """\
Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
"""


# =========================================================================== #
# Tests                                                                        #
# =========================================================================== #

class TestPatternManager(unittest.TestCase):

    def setUp(self):
        self.patterns_file = _ROOT / "extraction" / "patterns.yaml"
        self.pm = PatternManager(self.patterns_file)
        self.pm.load()

    def test_patterns_file_exists(self):
        self.assertTrue(self.patterns_file.exists(), "patterns.yaml must exist")

    def test_loads_expected_fields(self):
        expected = {"subject", "title", "name", "roll_no", "date"}
        loaded   = set(self.pm.fields)
        self.assertTrue(
            expected.issubset(loaded),
            f"Missing fields: {expected - loaded}"
        )

    def test_each_field_has_at_least_one_pattern(self):
        for field, defn in self.pm.definitions.items():
            self.assertGreater(
                len(defn.patterns), 0,
                f"Field '{field}' has no compiled patterns."
            )

    def test_reload(self):
        """reload() should not raise and should repopulate definitions."""
        self.pm.reload()
        self.assertGreater(len(self.pm.fields), 0)


class TestRegexEngineCore(unittest.TestCase):

    def setUp(self):
        pm = PatternManager(_ROOT / "extraction" / "patterns.yaml")
        pm.load()
        self.engine = RegexEngine(pm)

    # ---- Happy-path extractions ----------------------------------------

    def test_extract_subject(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertEqual(results["subject"].value, "Data Mining and Data Warehousing")

    def test_extract_title(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertEqual(results["title"].value, "Association Rule Mining")

    def test_extract_name(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertEqual(results["name"].value, "Vivek Rai")

    def test_extract_roll_no(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertEqual(results["roll_no"].value, "42")

    def test_extract_date(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertEqual(results["date"].value, "18/08/2026")

    def test_extract_semester(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertIsNotNone(results["semester"].value)

    # ---- Alternate keyword variations -----------------------------------

    def test_topic_as_title(self):
        results = self.engine.extract(SAMPLE_TEXT_VARIATIONS)
        self.assertIsNotNone(results["title"].value)

    def test_sub_as_subject(self):
        results = self.engine.extract(SAMPLE_TEXT_VARIATIONS)
        self.assertIsNotNone(results["subject"].value)

    def test_enrollment_as_roll_no(self):
        results = self.engine.extract(SAMPLE_TEXT_VARIATIONS)
        self.assertIsNotNone(results["roll_no"].value)

    def test_dash_date_format(self):
        """Date with dashes instead of slashes."""
        results = self.engine.extract(SAMPLE_TEXT_VARIATIONS)
        self.assertIsNotNone(results["date"].value)

    # ---- Graceful missing fields ----------------------------------------

    def test_missing_field_returns_none(self):
        results = self.engine.extract(SAMPLE_TEXT_NO_MATCHES)
        for field, res in results.items():
            self.assertIsNone(
                res.value,
                f"Field '{field}' should be None for unrelated text, got: {res.value!r}"
            )

    def test_empty_text_no_crash(self):
        """Engine must not raise on empty input."""
        results = self.engine.extract(SAMPLE_TEXT_EMPTY)
        for field, res in results.items():
            self.assertIsNone(res.value)

    # ---- matched_by reporting ------------------------------------------

    def test_matched_by_is_set_on_match(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        self.assertIsNotNone(results["name"].matched_by)
        self.assertTrue(results["name"].matched_by.startswith("Pattern"))

    def test_matched_by_none_on_no_match(self):
        results = self.engine.extract(SAMPLE_TEXT_NO_MATCHES)
        for field, res in results.items():
            self.assertIsNone(res.matched_by)

    # ---- Output formats ------------------------------------------------

    def test_to_dict_schema(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        d = results["subject"].to_dict()
        self.assertIn("field", d)
        self.assertIn("value", d)
        self.assertIn("matched_by", d)
        self.assertIn("pattern_str", d)
        self.assertIn("confidence", d)

    def test_extract_to_dict_simple(self):
        simple = self.engine.extract_to_dict(SAMPLE_TEXT_FULL)
        self.assertIsInstance(simple, dict)
        self.assertEqual(simple["name"], "Vivek Rai")

    # ---- Table formatter -----------------------------------------------

    def test_format_table_no_crash(self):
        results = self.engine.extract(SAMPLE_TEXT_FULL)
        table   = self.engine.format_table(results)
        self.assertIsInstance(table, str)
        self.assertIn("FIELD", table)
        self.assertIn("VALUE", table)
        self.assertIn("PATTERN", table)


# =========================================================================== #
# Standalone runner                                                            #
# =========================================================================== #

if __name__ == "__main__":
    unittest.main(verbosity=2)
