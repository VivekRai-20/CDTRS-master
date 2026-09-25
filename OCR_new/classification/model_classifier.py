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

    models/classifiers/document/vectorizer.pkl

Training
--------
    python fineTune/training/train.py --task classification

(documents in fineTune/datasets/classification/<CATEGORY>/ - see
fineTune/README.md).  This module only performs inference; DocumentProcessor
uses it when the files exist and it is more confident than the keyword rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from classification.base_classifier import BaseClassifier
from utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL_PATH = "models/classifiers/document"
_OCR_ROOT = Path(__file__).resolve().parents[1]


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

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._model is not None and self._vectorizer is not None

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
        model_dir = Path(cls_cfg.get("model_path", _DEFAULT_MODEL_PATH))
        if not model_dir.is_absolute():
            model_dir = _OCR_ROOT / model_dir  # relative to OCR_new, not the working folder

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

            if not vectorizer_file.exists():
                log.warning("'%s' is missing; the document classifier is not used.", vectorizer_file)
                self._model = None
                return
            with open(vectorizer_file, "rb") as fh:
                self._vectorizer = pickle.load(fh)

            label_file = model_dir / "label_encoder.pkl"
            if label_file.exists():
                with open(label_file, "rb") as fh:
                    self._label_encoder = pickle.load(fh)

            self._initialized = True
            log.info("ModelClassifier loaded from '%s'.", model_dir)

        except Exception as exc:
            log.warning("Failed to load ML classifier: %s", exc)
