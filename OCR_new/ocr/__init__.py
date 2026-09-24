"""
ocr/__init__.py
"""
from ocr.base_engine import BaseOCREngine
from ocr.paddle_engine import PaddleEngine, PaddleOCREngine
from ocr.handwriting_engine import HandwritingEngine
from ocr.text_type_detector import TextTypeDetector, TextType
from ocr.result_merger import merge
from ocr.ocr_pipeline import OCRPipeline

__all__ = [
    "BaseOCREngine",
    "PaddleEngine",
    "PaddleOCREngine",
    "HandwritingEngine",
    "TextTypeDetector",
    "TextType",
    "merge",
    "OCRPipeline",
]
