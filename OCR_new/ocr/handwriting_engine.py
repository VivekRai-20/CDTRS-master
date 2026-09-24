"""
ocr/handwriting_engine.py
--------------------------
Offline handwriting recognition engine.

This engine implements ``BaseOCREngine`` and uses a locally stored
TrOCR-style transformer model (Microsoft TrOCR or any compatible
Seq2Seq image-to-text model) for handwriting recognition.

Model storage
-------------
Place the model files under::

    models/handwriting/

Expected contents::

    models/handwriting/
    ├── config.json
    ├── tokenizer_config.json
    ├── vocab.json / merges.txt  (or equivalent tokenizer files)
    └── pytorch_model.bin  (or model.safetensors)

The engine will raise a clear error if the model directory is missing,
rather than attempting an online download.

Configuration
-------------
Relevant config.yaml keys::

    handwriting:
      enabled: true
      model_path: "models/handwriting"
      confidence_threshold: 0.5
      device: "cpu"      # "cpu" or "cuda"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ocr.base_engine import BaseOCREngine
from utils.logger import get_logger

log = get_logger(__name__)


class HandwritingEngine(BaseOCREngine):
    """
    Offline handwriting OCR engine backed by a local TrOCR-compatible model.

    The engine lazy-loads the model on the first call to ``initialize`` and
    processes one region image at a time via ``recognize``.
    """

    ENGINE_NAME = "HandwritingEngine"

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._confidence_threshold: float = 0.5
        self._model_path: Path | None = None
        self._initialized: bool = False

    # ------------------------------------------------------------------ #
    # Life-cycle                                                           #
    # ------------------------------------------------------------------ #

    def initialize(self, config: dict) -> None:
        """
        Load the local handwriting model.

        Parameters
        ----------
        config : dict
            Full application config.

        Raises
        ------
        FileNotFoundError
            If ``models/handwriting/`` does not exist or is empty.
        RuntimeError
            If the transformers package is not installed.
        """
        hw_cfg = config.get("handwriting", {})

        if not hw_cfg.get("enabled", True):
            log.info("Handwriting engine is DISABLED in config.")
            return

        model_path_str = hw_cfg.get("model_path", "models/handwriting")
        self._model_path = Path(model_path_str).resolve()
        self._confidence_threshold = float(
            hw_cfg.get("confidence_threshold", 0.5)
        )
        self._device = str(hw_cfg.get("device", "cpu"))

        self._check_model_exists()
        self._load_model()
        self._initialized = True
        log.info(
            "HandwritingEngine initialized from '%s' on device='%s'",
            self._model_path, self._device,
        )

    # ------------------------------------------------------------------ #
    # Core recognition                                                     #
    # ------------------------------------------------------------------ #

    def recognize(
        self, image: np.ndarray, page: int = 1
    ) -> list[dict[str, Any]]:
        """
        Run handwriting recognition on *image*.

        Parameters
        ----------
        image : np.ndarray
            BGR image (a single text region, not a full page).
        page : int
            1-indexed page number for embedding in results.

        Returns
        -------
        list[dict]
            OCR region dicts conforming to the base engine schema,
            with an additional ``text_type`` key set to ``"HANDWRITTEN"``.
        """
        if not self._initialized or self._model is None:
            log.warning(
                "HandwritingEngine not initialized. Returning empty result."
            )
            return []

        try:
            return self._run_inference(image, page)
        except Exception as exc:
            log.error("HandwritingEngine inference failed: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _check_model_exists(self) -> None:
        """Raise a clear error if the model directory is missing."""
        if self._model_path is None or not self._model_path.exists():
            raise FileNotFoundError(
                "\n"
                "========================================\n"
                "ERROR: Required model is not available locally.\n\n"
                "Model:\n"
                "  handwriting_recognition\n\n"
                "Expected location:\n"
                f"  {self._model_path}\n\n"
                "Offline mode is enabled.\n"
                "Automatic downloads are disabled.\n"
                "========================================\n"
                "Place a compatible TrOCR (or similar) model in the above\n"
                "directory and re-run the application.\n"
            )

        if not any(self._model_path.iterdir()):
            raise FileNotFoundError(
                f"Handwriting model directory exists but is empty: {self._model_path}"
            )

    def _load_model(self) -> None:
        """
        Load model and processor from the local model path.

        Uses the HuggingFace ``transformers`` library in offline mode
        (``local_files_only=True``).
        """
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            import torch

            log.info(
                "Loading handwriting model from '%s'…", self._model_path
            )
            self._processor = TrOCRProcessor.from_pretrained(
                str(self._model_path),
                local_files_only=True,
            )
            self._model = VisionEncoderDecoderModel.from_pretrained(
                str(self._model_path),
                local_files_only=True,
            )
            self._model.to(self._device)
            self._model.eval()

        except ImportError:
            raise RuntimeError(
                "The 'transformers' and 'torch' packages are required for "
                "handwriting recognition.\n"
                "Install them with:  pip install transformers torch"
            )

    def _run_inference(
        self, image: np.ndarray, page: int
    ) -> list[dict[str, Any]]:
        """Convert the image region to text using the loaded model."""
        import torch
        from PIL import Image as PILImage

        # Convert BGR → RGB → PIL
        rgb = image[:, :, ::-1] if image.ndim == 3 else image
        pil_img = PILImage.fromarray(rgb).convert("RGB")

        pixel_values = self._processor(
            images=pil_img, return_tensors="pt"
        ).pixel_values.to(self._device)

        with torch.no_grad():
            generated_ids = self._model.generate(pixel_values)

        generated_text: str = self._processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]

        generated_text = generated_text.strip()
        if not generated_text:
            return []

        h, w = image.shape[:2]
        return [
            {
                "text": generated_text,
                "confidence": self._confidence_threshold,
                "bbox": [0, 0, w, h],
                "page": page,
                "text_type": "HANDWRITTEN",
            }
        ]
