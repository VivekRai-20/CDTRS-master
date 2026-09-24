"""
testing/test_document_intelligence.py
--------------------------------------
Unit tests for the DocumentProcessor SDK module and DocumentResult schema.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from document_intelligence import DocumentProcessor, DocumentResult


class TestDocumentResult:
    """Test suite for DocumentResult structure and serialization."""

    def test_convenience_properties(self):
        res = DocumentResult(
            filename="sample.pdf",
            source_type="PDF",
            pages=2,
            full_text="Line 1\nLine 2",
            classification={"label": "TECHNICAL_REPORT", "confidence": 0.95},
        )
        assert res.document_type == "TECHNICAL_REPORT"
        assert res.text == "Line 1\nLine 2"
        assert res.pages == 2

    def test_default_document_type_fallback(self):
        res = DocumentResult(
            filename="sample.png",
            source_type="IMAGE",
            pages=1,
        )
        assert res.document_type == "IMAGE"

    def test_to_dict_matches_spec(self):
        res = DocumentResult(
            filename="document.pdf",
            source_type="PDF",
            pages=1,
            full_text="Hello World",
            regions=[{"page": 1, "text": "Hello World", "confidence": 0.99}],
            entities=[{"text": "World", "label": "LOCATION", "confidence": 0.9}],
            extracted_fields={"subject": "Math"},
        )
        d = res.to_dict()
        assert "document" in d
        assert d["document"]["filename"] == "document.pdf"
        assert d["document"]["pages"] == 1
        assert d["document"]["source_type"] == "PDF"
        assert "regions" in d
        assert "entities" in d
        assert "extracted_fields" in d
        assert "classification" in d
        assert "ocr" in d
        assert d["ocr"]["text"] == "Hello World"

    def test_save_writes_standard_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res = DocumentResult(
                filename="testdoc.pdf",
                source_type="PDF",
                pages=1,
                full_text="Some extracted text",
                regions=[{"page": 1, "text": "Some text", "confidence": 0.95}],
                classification={"label": "INVOICE", "confidence": 0.9},
                extracted_fields={"total": "$100"},
            )
            written = res.save(output_dir=tmpdir)
            assert "result.json" in written
            assert "ocr.txt" in written
            assert written["result.json"].exists()
            assert written["ocr.txt"].exists()

            # Verify content of ocr.txt
            content = written["ocr.txt"].read_text(encoding="utf-8")
            assert "Some extracted text" in content


class TestDocumentProcessor:
    """Test suite for DocumentProcessor initialization."""

    def test_init_with_default_config(self):
        processor = DocumentProcessor()
        assert processor.config is not None
        assert isinstance(processor.config, dict)

    def test_init_with_custom_config(self):
        custom = {"ocr": {"engine": "custom"}, "offline_mode": True}
        processor = DocumentProcessor(config=custom)
        assert processor.config["offline_mode"] is True
        assert processor.config["ocr"]["engine"] == "custom"

    def test_missing_file_raises_filenotfound(self):
        processor = DocumentProcessor()
        with pytest.raises(FileNotFoundError):
            processor.process("non_existent_file_12345.pdf")
