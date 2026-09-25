"""
testing/__init__.py
-------------------
OCR_new unit tests.  They use only the standard library (unittest); pytest is
not needed (it is not in imp.txt).  From the OCR_new folder:

    python -m unittest discover -s testing -t . -v      # all tests
    python -m unittest testing.test_text_type -v        # one file
"""

import tempfile
import unittest
from pathlib import Path


class TempDirTestCase(unittest.TestCase):
    """TestCase with a fresh temporary folder in ``self.tmp_path``."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
