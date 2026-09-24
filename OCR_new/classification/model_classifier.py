"""
classification/model_classifier.py
------------------------------------
Machine-learning based document classifier using a locally trained
scikit-learn model.

Model storage
-------------
::

    models/classifiers/document/classifier.pkl
    models/classifiers/document/label_encoder.pkl   (optional)

Training
--------
The model is trained via the fine-tuning framework (fineTune/).
This module only performs inference.

Supported algorithms (configured at training time):
  * Logistic Regression
  * SVM
  * Random Forest
  * Gradient Boosting
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from classification.base_classifier import BaseClassifier
from utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL_PATH = "models/classifiers/document"


class ModelClassifier(BaseClassifier):
    """
    ML-based document classifier using a local sklearn model.

    Falls back to UNKNOWN if no model is available.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    CLASSIFIER_NAME = "ModelClassifier"

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._model = None
        self._vectorizer = None
        self._label_encoder = None
        self._initialized = False
        self._load_model()

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def classify(self, text: str) -> dict[str, Any]:
        """
        Classify *text* using the local ML model.

        Returns UNKNOWN if no model is available.
        """
        if not self._initialized or self._model is None:
            return self._result("UNKNOWN", 0.0)

        if not text.strip():
            return self._result("UNKNOWN", 0.0)

        try:
            X = self._vectorizer.transform([text])
            label_idx = int(self._model.predict(X)[0])
            proba = self._model.predict_proba(X)[0]
            confidence = float(proba[label_idx])

            if self._label_encoder is not None:
                label = str(self._label_encoder.inverse_transform([label_idx])[0])
            else:
                label = str(label_idx)

            log.debug("ModelClassifier: '%s' (confidence=%.3f)", label, confidence)
            return self._result(label, confidence)

        except Exception as exc:
            log.warning("ModelClassifier inference failed: %s", exc)
            return self._result("UNKNOWN", 0.0)

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _load_model(self) -> None:
        cls_cfg = self._config.get("classification", {})
        model_dir = Path(cls_cfg.get("model_path", _DEFAULT_MODEL_PATH)).resolve()

        model_file = model_dir / "classifier.pkl"
        vectorizer_file = model_dir / "vectorizer.pkl"

        if not model_file.exists():
            log.debug(
                "No ML classifier found at '%s'. ModelClassifier will return UNKNOWN.",
                model_file,
            )
            return

        try:
            import pickle
            with open(model_file, "rb") as fh:
                self._model = pickle.load(fh)

            if vectorizer_file.exists():
                with open(vectorizer_file, "rb") as fh:
                    self._vectorizer = pickle.load(fh)
            else:
                # Build a simple TF-IDF vectorizer as placeholder
                from sklearn.feature_extraction.text import TfidfVectorizer
                self._vectorizer = TfidfVectorizer()
                log.warning(
                    "No vectorizer found. Classification may be inaccurate."
                )

            label_file = model_dir / "label_encoder.pkl"
            if label_file.exists():
                with open(label_file, "rb") as fh:
                    self._label_encoder = pickle.load(fh)

            self._initialized = True
            log.info("ModelClassifier loaded from '%s'.", model_dir)

        except Exception as exc:
            log.warning("Failed to load ML classifier: %s", exc)
