"""
classification/base_classifier.py
-----------------------------------
Abstract base class that all document classifiers must implement.

Every classifier in the ``classification/`` package inherits from
``BaseClassifier`` and implements ``classify(text)``.

This ensures the rest of the pipeline can swap classifiers without
touching any downstream code.

Result schema
-------------
{
    "label":      str,    # predicted document category
    "confidence": float,  # 0.0 – 1.0
    "method":     str     # name of the classifier that produced the result
}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseClassifier(ABC):
    """
    Abstract document classifier.

    All concrete classifiers must implement ``classify``.
    """

    # Human-readable name (override in subclasses)
    CLASSIFIER_NAME: str = "BaseClassifier"

    @abstractmethod
    def classify(self, text: str) -> dict[str, Any]:
        """
        Classify *text* into a document category.

        Parameters
        ----------
        text : str
            Full OCR-extracted document text.

        Returns
        -------
        dict with keys ``label`` (str), ``confidence`` (float),
        ``method`` (str).
        """
        ...

    def _result(self, label: str, confidence: float) -> dict[str, Any]:
        """Helper to build a standardised result dict."""
        return {
            "label":      label,
            "confidence": round(float(confidence), 4),
            "method":     self.CLASSIFIER_NAME,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.CLASSIFIER_NAME}'>"
