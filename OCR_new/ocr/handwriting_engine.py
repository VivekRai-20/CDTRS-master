"""
ocr/handwriting_engine.py
--------------------------
Offline handwriting recognition with a local TrOCR model.

PaddleOCR reads every text line first.  Lines that the text-type detector marks
as HANDWRITTEN are then read again by this engine (see
document_intelligence.DocumentProcessor), because TrOCR is trained on
handwriting while PaddleOCR's recogniser is trained on print.

Model storage
-------------
    models/handwriting/
    ├── active.txt                     name of the folder to use, e.g. "v2"
    ├── trocr-small-handwritten/       base model (fineTune/download_base_model.py)
    └── v1/, v2/, ...                  your fine-tuned versions (fineTune/training/train.py)

Each model folder holds a Hugging Face TrOCR model (config.json, weights,
tokenizer and preprocessor files) plus model_meta.json.

Nothing is ever downloaded here: when no model is installed the engine reports
itself unavailable and the OCR simply keeps PaddleOCR's text.

Configuration (config.yaml)
---------------------------
    handwriting:
      enabled: true
      model_path: "models/handwriting"
      device: "cpu"
      num_beams: 3
      max_new_tokens: 64
      max_lines_per_page: 80          # at most this many lines re-read per page
      min_confidence: 0.5             # ignore TrOCR results below this

A line's PaddleOCR text is replaced only when the line is HANDWRITTEN (or
UNKNOWN and PaddleOCR was unsure) and TrOCR is at least as confident as
PaddleOCR.  Both readings are kept on the region.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from ocr.base_engine import BaseOCREngine
from utils.logger import get_logger

log = get_logger(__name__)

_OCR_ROOT = Path(__file__).resolve().parents[1]


# ──────────────────────────────────────────────────────────────────────────────
# Model location / loading (shared with fineTune/)
# ──────────────────────────────────────────────────────────────────────────────

def _is_model_dir(folder: Path) -> bool:
    return folder.is_dir() and (folder / "config.json").exists() and any(
        (folder / name).exists() for name in ("model.safetensors", "pytorch_model.bin")
    )


def handwriting_root(config: Optional[dict] = None) -> Path:
    rel = ((config or {}).get("handwriting") or {}).get("model_path", "models/handwriting")
    path = Path(rel)
    return path if path.is_absolute() else _OCR_ROOT / path


def resolve_model_dir(config: Optional[dict] = None, version: Optional[str] = None) -> Optional[Path]:
    """The handwriting model folder to use, or None when none is active.

    Order: an explicit *version* folder, the folder named in
    models/handwriting/active.txt, or model_path itself when it directly
    holds a model.  Downloaded or trained models that are not activated are
    never picked up by accident."""
    root = handwriting_root(config)
    if version:
        candidate = Path(version)
        candidate = candidate if candidate.is_absolute() else root / version
        return candidate if _is_model_dir(candidate) else None
    if _is_model_dir(root):
        return root
    active = root / "active.txt"
    if active.exists():
        name = active.read_text(encoding="utf-8").strip()
        if name and _is_model_dir(root / name):
            return root / name
        if name:
            log.warning("models/handwriting/active.txt names '%s', which is not a model folder.", name)
    return None


def list_models(config: Optional[dict] = None) -> list[Path]:
    """All installed handwriting model folders (base and fine-tuned)."""
    root = handwriting_root(config)
    if not root.is_dir():
        return []
    return sorted(f for f in root.iterdir() if _is_model_dir(f))


def load_trocr_processor(model_dir: Path):
    """TrOCR processor (image preprocessing + tokenizer) from a local folder.

    The tokenizer is loaded with the class named in tokenizer_config.json
    (e.g. XLMRobertaTokenizer for trocr-small, RobertaTokenizer for
    trocr-base); the generic auto-loader cannot build it from the original
    sentencepiece file."""
    import json

    import transformers
    from transformers import AutoImageProcessor, AutoTokenizer, TrOCRProcessor

    model_dir = Path(model_dir)
    image_processor = AutoImageProcessor.from_pretrained(str(model_dir), local_files_only=True)
    tokenizer = None
    cfg_file = model_dir / "tokenizer_config.json"
    if cfg_file.exists():
        class_name = (json.loads(cfg_file.read_text(encoding="utf-8")).get("tokenizer_class") or "").strip()
        tokenizer_cls = getattr(transformers, class_name, None) or getattr(
            transformers, class_name.replace("Fast", ""), None
        )
        if tokenizer_cls is not None:
            try:
                tokenizer = tokenizer_cls.from_pretrained(str(model_dir), local_files_only=True)
            except Exception as exc:
                log.debug("%s could not load the tokenizer: %s", class_name, exc)
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    return TrOCRProcessor(image_processor=image_processor, tokenizer=tokenizer)


def load_trocr(model_dir: Path, device: str = "cpu"):
    """Load a TrOCR processor + model from a local folder (never downloads)."""
    from transformers import VisionEncoderDecoderModel
    from transformers.utils import logging as hf_logging

    hf_logging.set_verbosity_error()  # e.g. "encoder.pooler ... newly initialized" (unused layer)
    processor = load_trocr_processor(model_dir)
    model = VisionEncoderDecoderModel.from_pretrained(str(model_dir), local_files_only=True)
    tokenizer = processor.tokenizer
    config = model.config
    gen = model.generation_config

    def first(*values):
        for value in values:
            if value is not None:
                return value
        return None

    # Generation and training need these three ids; depending on the
    # checkpoint they live on the config, the decoder config or nowhere.
    start = first(getattr(gen, "decoder_start_token_id", None),
                  getattr(config, "decoder_start_token_id", None),
                  getattr(getattr(config, "decoder", None), "decoder_start_token_id", None),
                  tokenizer.cls_token_id, tokenizer.bos_token_id)
    pad = first(getattr(gen, "pad_token_id", None), getattr(config, "pad_token_id", None),
                tokenizer.pad_token_id)
    eos = first(getattr(gen, "eos_token_id", None), getattr(config, "eos_token_id", None),
                tokenizer.sep_token_id, tokenizer.eos_token_id)
    gen.decoder_start_token_id, gen.pad_token_id, gen.eos_token_id = start, pad, eos
    for name, value in (("decoder_start_token_id", start), ("pad_token_id", pad), ("eos_token_id", eos)):
        try:
            setattr(config, name, value)
        except Exception:
            pass
    model.to(device)
    model.eval()
    return processor, model


def prepare_line_image(image: Any) -> np.ndarray:
    """Clean one text-line crop before TrOCR reads it (training and reading
    use the same step):

    * grayscale - TrOCR was trained on grayscale-looking scans; coloured ink
      and paper confuse it;
    * ruled-paper lines and underlines are painted out;
    * the crop is trimmed to the band of the line itself - PaddleOCR's boxes
      often include parts of the lines above and below, which makes TrOCR
      invent text.

    Returns an RGB uint8 array."""
    import cv2
    from PIL import Image as PILImage

    if isinstance(image, PILImage.Image):
        image = np.asarray(image.convert("RGB"))[:, :, ::-1]
    arr = np.asarray(image)
    g = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr.copy()
    h, w = g.shape[:2]
    if h < 8 or w < 8:
        return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)
    _, ink = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    rules = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 4), 1)))
    rules = cv2.dilate(rules, np.ones((3, 1), np.uint8))
    text = cv2.subtract(ink, rules)
    background = int(np.median(g[ink == 0])) if (ink == 0).any() else 255
    g = g.copy()
    g[rules > 0] = background

    rows = text.sum(axis=1).astype(float)
    if rows.sum() == 0:
        return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)
    k = max(3, h // 12) | 1
    smooth = np.convolve(rows, np.ones(k) / k, mode="same")
    inside = smooth > 0.12 * smooth.max()
    bands, start = [], None
    for i, flag in enumerate(inside):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            bands.append((start, i))
            start = None
    if start is not None:
        bands.append((start, h))

    def weight(band: tuple[int, int]) -> float:
        top, bottom = band
        centre = (top + bottom) / 2.0
        return rows[top:bottom].sum() * (1.0 - 0.5 * abs(centre - h / 2.0) / (h / 2.0))

    top, bottom = max(bands, key=weight)
    pad = int(0.25 * (bottom - top)) + 2
    top, bottom = max(0, top - pad), min(h, bottom + pad)
    cols = np.where(text[top:bottom].sum(axis=0) > 0)[0]
    left, right = (max(0, cols[0] - pad), min(w, cols[-1] + pad + 1)) if cols.size else (0, w)
    return cv2.cvtColor(g[top:bottom, left:right], cv2.COLOR_GRAY2RGB)


def to_pil_rgb(image: Any):
    """numpy BGR / gray array or PIL image -> RGB PIL image."""
    from PIL import Image as PILImage

    if isinstance(image, PILImage.Image):
        return image.convert("RGB")
    arr = np.asarray(image)
    if arr.ndim == 2:
        return PILImage.fromarray(arr).convert("RGB")
    return PILImage.fromarray(np.ascontiguousarray(arr[:, :, ::-1])).convert("RGB")


# ──────────────────────────────────────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────────────────────────────────────

class HandwritingEngine(BaseOCREngine):
    """TrOCR handwriting recogniser for single text-line images."""

    ENGINE_NAME = "HandwritingEngine"

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._num_beams = 3
        self._max_new_tokens = 64
        self._model_path: Optional[Path] = None
        self._initialized = False

    @property
    def model_path(self) -> Optional[Path]:
        return self._model_path

    @staticmethod
    def is_available(config: dict) -> bool:
        hw_cfg = config.get("handwriting", {})
        return bool(hw_cfg.get("enabled", True)) and resolve_model_dir(config) is not None

    # ------------------------------------------------------------------ #
    # Life-cycle                                                           #
    # ------------------------------------------------------------------ #

    def initialize(self, config: dict) -> None:
        hw_cfg = config.get("handwriting", {})
        if not hw_cfg.get("enabled", True):
            log.info("Handwriting engine is disabled in config.")
            return
        self._model_path = resolve_model_dir(config, hw_cfg.get("version"))
        if self._model_path is None:
            raise FileNotFoundError(
                "No handwriting model is installed under "
                f"{handwriting_root(config)}.\n"
                "Download the base model once with:\n"
                "    python fineTune/download_base_model.py\n"
                "Automatic downloads are disabled (offline mode)."
            )
        self._device = str(hw_cfg.get("device", "cpu"))
        self._num_beams = int(hw_cfg.get("num_beams", 3))
        self._max_new_tokens = int(hw_cfg.get("max_new_tokens", 64))
        log.info("Loading handwriting model from '%s' ...", self._model_path)
        self._processor, self._model = load_trocr(self._model_path, self._device)
        self._initialized = True
        log.info("HandwritingEngine ready (%s, device=%s).", self._model_path.name, self._device)

    # ------------------------------------------------------------------ #
    # Recognition                                                          #
    # ------------------------------------------------------------------ #

    def read_lines(self, images: Iterable[Any], batch_size: int = 8, prepare: bool = True) -> list[tuple[str, float]]:
        """Read text-line images (numpy BGR/gray or PIL).
        Returns [(text, confidence 0..1), ...] in the same order."""
        if not self._initialized:
            return []
        import torch
        from PIL import Image as PILImage

        if prepare:
            pil_images = [PILImage.fromarray(prepare_line_image(img)) for img in images]
        else:
            pil_images = [to_pil_rgb(img) for img in images]
        results: list[tuple[str, float]] = []
        for start in range(0, len(pil_images), batch_size):
            batch = pil_images[start:start + batch_size]
            pixel_values = self._processor(images=batch, return_tensors="pt").pixel_values.to(self._device)
            with torch.no_grad():
                out = self._model.generate(
                    pixel_values,
                    num_beams=self._num_beams,
                    max_new_tokens=self._max_new_tokens,
                    return_dict_in_generate=True,
                    output_scores=True,
                )
            texts = self._processor.batch_decode(out.sequences, skip_special_tokens=True)
            confidences = self._confidences(out, len(batch))
            results.extend((t.strip(), c) for t, c in zip(texts, confidences))
        return results

    def _confidences(self, out: Any, count: int) -> list[float]:
        """Average per-token probability of each generated line."""
        try:
            scores = getattr(out, "sequences_scores", None)
            if scores is not None:  # beam search: length-normalised log-probability
                return [round(float(math.exp(float(s))), 4) for s in scores]
            transition = self._model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)
            generated = out.sequences[:, -transition.shape[1]:]
            pad = self._model.generation_config.pad_token_id
            values = []
            for row_scores, row_tokens in zip(transition, generated):
                logps = [
                    float(s) for s, t in zip(row_scores, row_tokens)
                    if int(t) != pad and math.isfinite(float(s))
                ]
                values.append(round(math.exp(sum(logps) / len(logps)), 4) if logps else 0.0)
            return values
        except Exception as exc:  # pragma: no cover - depends on transformers internals
            log.debug("Could not compute handwriting confidence: %s", exc)
            return [0.5] * count

    def recognize(self, image: np.ndarray, page: int = 1) -> list[dict[str, Any]]:
        """BaseOCREngine interface: *image* is ONE text-line crop."""
        if not self._initialized:
            log.warning("HandwritingEngine not initialized. Returning empty result.")
            return []
        try:
            text, confidence = self.read_lines([image])[0]
        except Exception as exc:
            log.error("HandwritingEngine inference failed: %s", exc)
            return []
        if not text:
            return []
        h, w = image.shape[:2]
        return [{
            "text": text,
            "confidence": confidence,
            "bbox": [0, 0, w, h],
            "page": page,
            "text_type": "HANDWRITTEN",
        }]
