"""
testing/test_classification.py
--------------------------------
Unit tests for the classification module.
"""

from __future__ import annotations

import unittest

from classification.rule_classifier import RuleClassifier
from classification.base_classifier import BaseClassifier


class TestRuleClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = RuleClassifier(config={})

    def test_classify_returns_dict(self):
        result = self.clf.classify("This is a test document.")
        assert isinstance(result, dict)

    def test_classify_has_required_keys(self):
        result = self.clf.classify("invoice total amount gst")
        assert "label" in result
        assert "confidence" in result
        assert "method" in result

    def test_classify_invoice_text(self):
        text = "Invoice Total Amount: Rs. 5000 GST Vendor: ABC Corp"
        result = self.clf.classify(text)
        assert result["label"] == "INVOICE"
        assert result["confidence"] > 0.0

    def test_classify_leave_text(self):
        text = "I am requesting leave for two days due to illness. I will be absent."
        result = self.clf.classify(text)
        assert result["label"] == "LEAVE_APPLICATION"

    def test_classify_empty_text_returns_unknown(self):
        result = self.clf.classify("")
        assert result["label"] == "UNKNOWN"
        assert result["confidence"] == 0.0

    def test_confidence_in_range(self):
        result = self.clf.classify("Some random text")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_method_field(self):
        result = self.clf.classify("test")
        assert result["method"] == "RuleClassifier"


class TestBaseClassifierInterface(unittest.TestCase):
    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            BaseClassifier()
