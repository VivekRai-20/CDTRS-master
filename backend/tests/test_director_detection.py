"""
Unit tests for the Director-instruction detector in backend/ocr_adapter.py
(standard-library unittest; no OCR models or database needed).

    cd backend
    python tests/test_director_detection.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_adapter import _detect_director_instruction  # noqa: E402


def region(text, y, kind="HANDWRITTEN", conf=0.8, x=100):
    return {"text": text, "bbox": [x, y, x + 400, y + 40], "page": 1, "text_type": kind, "confidence": conf}


class DirectorInstructionTests(unittest.TestCase):
    def test_note_on_printed_letter_is_found(self):
        regions = [
            region("Put up for discussion with HOD", 60, conf=0.7),
            region("GOVERNMENT OF INDIA", 200, "PRINTED", 0.99),
            region("Subject: Release of funds", 260, "PRINTED", 0.99),
        ]
        self.assertEqual(_detect_director_instruction(regions), "Put up for discussion with HOD")

    def test_note_over_two_lines_is_returned_whole(self):
        regions = [region("Pl. examine and", 60, conf=0.6), region("put up", 105, conf=0.6)]
        self.assertEqual(_detect_director_instruction(regions), "Pl. examine and put up")

    def test_address_lines_are_ignored(self):
        regions = [region("To, The Director", 60), region("Respected Sir", 110)]
        self.assertIsNone(_detect_director_instruction(regions))

    def test_handwritten_notes_without_instruction_are_not_a_remark(self):
        regions = [
            region("Chemical kinetics is branch of chemistry", 60, conf=0.7),
            region("rate and the mechanism of the reaction", 110, conf=0.6),
        ]
        self.assertIsNone(_detect_director_instruction(regions))

    def test_printed_text_is_never_a_remark(self):
        self.assertIsNone(_detect_director_instruction([region("Please process urgently", 60, "PRINTED", 0.99)]))


if __name__ == "__main__":
    unittest.main()
