"""
testing/test_extraction.py
---------------------------
Unit tests for the extraction module (NER, regex, entity extractor).
"""

from __future__ import annotations

import unittest

from nlp.ner_engine import NEREngine
from nlp.text_cleaner import clean, split_sentences
from nlp.entity_normalizer import normalize_entity, normalize_entities
from extraction.entity_extractor import EntityExtractor


class TestNEREngine(unittest.TestCase):
    def setUp(self):
        self.ner = NEREngine(config={})
        self.ner.initialize()

    def test_extract_returns_list(self):
        result = self.ner.extract("Send the report to john@example.com")
        assert isinstance(result, list)

    def test_extract_email(self):
        result = self.ner.extract("Contact us at support@company.org")
        emails = [e for e in result if e["label"] == "EMAIL"]
        assert len(emails) >= 1
        assert "support@company.org" in emails[0]["text"]

    def test_extract_date(self):
        result = self.ner.extract("Meeting on 20 September 2026")
        dates = [e for e in result if e["label"] == "DATE"]
        assert len(dates) >= 1

    def test_extract_empty_text(self):
        result = self.ner.extract("")
        assert result == []

    def test_entity_has_required_keys(self):
        result = self.ner.extract("Call +91 98765 43210")
        if result:
            ent = result[0]
            assert "text" in ent
            assert "label" in ent
            assert "confidence" in ent


class TestTextCleaner(unittest.TestCase):
    def test_clean_basic(self):
        text = "Hello   World\n\n\nThis is  a test."
        result = clean(text)
        assert "Hello World" in result

    def test_clean_empty_returns_empty(self):
        assert clean("") == ""

    def test_clean_removes_control_chars(self):
        text = "Hello\x00World"
        result = clean(text)
        assert "\x00" not in result

    def test_split_sentences(self):
        text = "This is sentence one. This is sentence two! And three?"
        sentences = split_sentences(text)
        assert len(sentences) >= 2


class TestEntityNormalizer(unittest.TestCase):
    def test_normalize_email(self):
        result = normalize_entity("  User@EXAMPLE.COM  ", "EMAIL")
        assert result == "user@example.com"

    def test_normalize_phone(self):
        result = normalize_entity("+91 98765 43210", "PHONE")
        assert result.replace(" ", "") == "+919876543210"

    def test_normalize_unknown_label_returns_stripped(self):
        result = normalize_entity("  some text  ", "CUSTOM")
        assert result == "some text"

    def test_normalize_entities_list(self):
        entities = [
            {"text": "user@test.com", "label": "EMAIL"},
            {"text": "20 September", "label": "DATE"},
        ]
        result = normalize_entities(entities)
        assert "normalized_text" in result[0]
        assert result[0]["normalized_text"] == "user@test.com"


class TestEntityExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = EntityExtractor(config={})

    def test_extract_returns_dict(self):
        result = self.extractor.extract("Contact at user@test.com")
        assert isinstance(result, dict)
        assert "entities" in result
        assert "extracted_fields" in result

    def test_extract_email_field(self):
        result = self.extractor.extract("Send to admin@company.org")
        fields = result.get("extracted_fields", {})
        assert "emails" in fields

    def test_extract_empty_text(self):
        result = self.extractor.extract("")
        assert result["entities"] == []
