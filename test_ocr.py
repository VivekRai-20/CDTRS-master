import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_OCR_DIR = _PROJECT_ROOT / "OCR_new"
sys.path.insert(0, str(_OCR_DIR))

from document_intelligence import DocumentProcessor

processor = DocumentProcessor()
res = processor.process("OCR_new/temp/handwritten_test.png", mode="full")

print(res.text_types)
print(res.regions)
