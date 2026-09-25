"""
testing/test_document.py
-------------------------
Unit tests for the document loading and normalisation module.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import unittest

from testing import TempDirTestCase

from document.file_detector import detect, DocumentType
from document.document_normalizer import normalize, NormalizedDocument, PageImage


# ──────────────────────────────────────────────────────────────────────────────
# File detection
# ──────────────────────────────────────────────────────────────────────────────

class TestFileDetector(TempDirTestCase):
    def test_detect_pdf_by_extension(self):
        tmp_path = self.tmp_path
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        assert detect(pdf_file) == DocumentType.PDF

    def test_detect_png_by_extension(self):
        tmp_path = self.tmp_path
        img_file = tmp_path / "sample.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        assert detect(img_file) == DocumentType.IMAGE

    def test_detect_jpg_by_extension(self):
        tmp_path = self.tmp_path
        img_file = tmp_path / "sample.jpg"
        img_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        assert detect(img_file) == DocumentType.IMAGE

    def test_detect_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            detect("/nonexistent/file.pdf")


# ──────────────────────────────────────────────────────────────────────────────
# Document normalizer
# ──────────────────────────────────────────────────────────────────────────────

class TestDocumentNormalizer(TempDirTestCase):
    def test_normalize_text_file(self):
        tmp_path = self.tmp_path
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello, world!", encoding="utf-8")

        doc = normalize(txt_file)
        assert isinstance(doc, NormalizedDocument)
        assert doc.source_format == "TEXT"
        assert doc.page_count == 1
        assert isinstance(doc.pages[0], PageImage)
        assert "Hello, world!" in doc.pages[0].metadata.get("native_text", "")

    def test_normalize_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            normalize("/nonexistent/file.pdf")

    def test_normalized_document_repr(self):
        tmp_path = self.tmp_path
        txt_file = tmp_path / "doc.txt"
        txt_file.write_text("test", encoding="utf-8")
        doc = normalize(txt_file)
        assert "NormalizedDocument" in repr(doc)

    def test_get_page(self):
        tmp_path = self.tmp_path
        txt_file = tmp_path / "doc.txt"
        txt_file.write_text("content", encoding="utf-8")
        doc = normalize(txt_file)
        page = doc.get_page(1)
        assert page is not None
        assert page.page_number == 1

    def test_get_nonexistent_page_returns_none(self):
        tmp_path = self.tmp_path
        txt_file = tmp_path / "doc.txt"
        txt_file.write_text("content", encoding="utf-8")
        doc = normalize(txt_file)
        assert doc.get_page(99) is None
