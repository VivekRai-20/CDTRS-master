"""
ocr/paddle_engine.py
--------------------
PaddleOCR implementation of BaseOCREngine.

Supports PaddleOCR 2.x and 3.x automatically.

PaddleOCR 3.x API changes (vs 2.x):
  - use_angle_cls   → use_textline_orientation
  - det_model_dir   → text_detection_model_dir
  - rec_model_dir   → text_recognition_model_dir
  - cls_model_dir   → textline_orientation_model_dir
  - show_log        → removed
  - download_font   → removed
  - ocr(img, cls=..)→ ocr(img)  (cls param removed in 3.x)

This engine detects the installed version at runtime and uses the
correct parameters automatically.
"""

from __future__ import annotations

import inspect
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from ocr.base_engine import BaseOCREngine
from utils.logger import get_logger
from utils.offline_checker import abort_if_models_missing

log = get_logger(__name__)


class PaddleEngine(BaseOCREngine):
    """
    PaddleOCR-backed OCR engine.
    Compatible with PaddleOCR 2.x and 3.x.
    """

    ENGINE_NAME = "PaddleOCR"

    def __init__(self) -> None:
        self._ocr = None
        self._config: dict = {}
        self._major_version: int = 0

    # ------------------------------------------------------------------ #
    # Life-cycle                                                           #
    # ------------------------------------------------------------------ #

    def initialize(self, config: dict) -> None:
        """
        Load PaddleOCR with local model paths.
        Auto-detects 2.x vs 3.x API and uses correct parameter names.
        """
        self._config = config
        paddle_cfg = config.get("paddleocr", {})

        # --- Offline guard -------------------------------------------------
        abort_if_models_missing(config)

        # --- Import --------------------------------------------------------
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ImportError(
                "paddleocr package not installed. Run: pip install -r requirements.txt"
            ) from exc

        # --- Detect version ------------------------------------------------
        import paddleocr as _poc
        version_str = getattr(_poc, "__version__", "2.0.0")
        self._major_version = int(version_str.split(".")[0])
        log.info("PaddleOCR version: %s (major: %d)", version_str, self._major_version)

        # --- Resolve model paths -------------------------------------------
        root = Path(__file__).resolve().parents[1]

        def abs_path(rel: str) -> str:
            """Absolute model dir, only if it actually holds model files.

            PaddleOCR 2.x downloads into an empty model dir, which fails
            offline; with no dir given it uses its own ~/.paddleocr cache.
            """
            p = Path(rel)
            full = root / p if not p.is_absolute() else p
            if not full.is_dir():
                return None
            has_model = any(
                f.suffix.lower() in (".pdmodel", ".pdiparams") for f in full.iterdir()
            )
            return str(full) if has_model else None

        det_dir = abs_path(paddle_cfg.get("det_model_dir", "models/paddleocr/det"))
        rec_dir = abs_path(paddle_cfg.get("rec_model_dir", "models/paddleocr/rec"))
        cls_dir = abs_path(paddle_cfg.get("cls_model_dir", "models/paddleocr/cls"))

        # --- Get valid constructor params for this version -----------------
        sig_params = inspect.signature(PaddleOCR.__init__).parameters
        valid_params = set(sig_params.keys()) - {"self", "kwargs", "args"}
        if self._major_version < 3 and any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig_params.values()
        ):
            # PaddleOCR 2.x takes everything through **kwargs (argparse names).
            valid_params |= {
                "use_gpu", "use_angle_cls", "show_log", "ocr_version",
                "det_model_dir", "rec_model_dir", "cls_model_dir",
                "det_db_thresh", "det_db_box_thresh", "det_db_unclip_ratio",
                "det_limit_side_len", "det_limit_type", "drop_score",
            }

        # --- Build kwargs --------------------------------------------------
        lang        = paddle_cfg.get("lang", "en")
        ocr_version = paddle_cfg.get("ocr_version", "PP-OCRv4")
        use_gpu     = paddle_cfg.get("use_gpu", False)

        kwargs: dict[str, Any] = {"lang": lang}

        if "use_gpu" in valid_params:
            kwargs["use_gpu"] = use_gpu

        if self._major_version >= 3:
            # PaddleOCR 3.x:
            import os
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

            if "ocr_version" in valid_params and ocr_version:
                kwargs["ocr_version"] = ocr_version

            # Pipeline toggles
            if "use_doc_unwarping" in valid_params:
                kwargs["use_doc_unwarping"] = paddle_cfg.get("use_doc_unwarping", False)
            if "use_doc_orientation_classify" in valid_params:
                kwargs["use_doc_orientation_classify"] = paddle_cfg.get("use_doc_orientation_classify", False)
            if "use_textline_orientation" in valid_params:
                kwargs["use_textline_orientation"] = paddle_cfg.get("use_textline_orientation", True)

            # Detection & recognition parameters for handwriting
            if "text_det_unclip_ratio" in valid_params and "text_det_unclip_ratio" in paddle_cfg:
                kwargs["text_det_unclip_ratio"] = float(paddle_cfg["text_det_unclip_ratio"])
            if "text_det_box_thresh" in valid_params and "text_det_box_thresh" in paddle_cfg:
                kwargs["text_det_box_thresh"] = float(paddle_cfg["text_det_box_thresh"])
            if "text_det_thresh" in valid_params and "text_det_thresh" in paddle_cfg:
                kwargs["text_det_thresh"] = float(paddle_cfg["text_det_thresh"])
            if "text_det_limit_side_len" in valid_params and "text_det_limit_side_len" in paddle_cfg:
                kwargs["text_det_limit_side_len"] = int(paddle_cfg["text_det_limit_side_len"])
            if "text_det_limit_type" in valid_params and "text_det_limit_type" in paddle_cfg:
                kwargs["text_det_limit_type"] = str(paddle_cfg["text_det_limit_type"])
            if "text_rec_score_thresh" in valid_params:
                kwargs["text_rec_score_thresh"] = float(paddle_cfg.get("drop_score", 0.35))
        else:
            # PaddleOCR 2.x parameter names
            if "use_angle_cls" in valid_params:
                kwargs["use_angle_cls"] = paddle_cfg.get(
                    "use_angle_cls", paddle_cfg.get("use_textline_orientation", True)
                )
            if "show_log" in valid_params:
                kwargs["show_log"] = paddle_cfg.get("show_log", False)
            if "download_font" in valid_params:
                kwargs["download_font"] = False
            # 2.x only knows PP-OCR up to v4 (v5 is a 3.x model family).
            if "ocr_version" in valid_params and ocr_version:
                kwargs["ocr_version"] = ocr_version if ocr_version in (
                    "PP-OCR", "PP-OCRv2", "PP-OCRv3", "PP-OCRv4"
                ) else "PP-OCRv4"
            # Same detection tuning as the 3.x settings in config.yaml.
            for cfg_key, arg, cast in (
                ("text_det_thresh", "det_db_thresh", float),
                ("text_det_box_thresh", "det_db_box_thresh", float),
                ("text_det_unclip_ratio", "det_db_unclip_ratio", float),
                ("text_det_limit_side_len", "det_limit_side_len", int),
                ("text_det_limit_type", "det_limit_type", str),
            ):
                if arg in valid_params and cfg_key in paddle_cfg:
                    kwargs[arg] = cast(paddle_cfg[cfg_key])
            if "drop_score" in valid_params and "drop_score" in paddle_cfg:
                kwargs["drop_score"] = float(paddle_cfg["drop_score"])
            # Paddle keeps working memory for every input shape it has seen,
            # and a batch of long text lines needs gigabytes.  One line at a
            # time keeps that small (see _limit_recognition_shapes).
            kwargs["rec_batch_num"] = int(paddle_cfg.get("rec_batch_num", 1))
            if det_dir and "det_model_dir" in valid_params:
                kwargs["det_model_dir"] = det_dir
            if rec_dir and "rec_model_dir" in valid_params:
                kwargs["rec_model_dir"] = rec_dir
            if cls_dir and "cls_model_dir" in valid_params:
                kwargs["cls_model_dir"] = cls_dir

        log.info("Initialising PaddleOCR %s (version=%s, lang=%s) …", version_str, ocr_version, lang)
        log.debug("Constructor kwargs: %s", kwargs)
        self._ocr = PaddleOCR(**kwargs)
        if self._major_version < 3:
            self._limit_recognition_shapes(paddle_cfg)
        log.info("PaddleOCR initialised successfully.")

    # ------------------------------------------------------------------ #
    # Memory: bounded set of input shapes                                  #
    # ------------------------------------------------------------------ #

    def _limit_recognition_shapes(self, paddle_cfg: dict) -> None:
        """Round the recogniser's input width up to a few fixed sizes.

        Paddle Inference keeps the buffers of every input shape it has run,
        and never frees them.  PaddleOCR sizes each text line to its own
        width, so every new line length costs memory until the process runs
        out (a busy server was killed this way).  Using widths that are
        multiples of ``rec_ratio_step`` x 48 px (and at most
        ``rec_max_ratio`` x 48 px - longer lines are narrowed to fit) keeps
        the number of shapes, and so the memory, small and fixed.
        """
        recognizer = getattr(self._ocr, "text_recognizer", None)
        original = getattr(recognizer, "resize_norm_img", None)
        if recognizer is None or original is None:
            return
        step = float(paddle_cfg.get("rec_ratio_step", 8))
        max_ratio = float(paddle_cfg.get("rec_max_ratio", 32))
        if step <= 0:
            return

        def bucketed(img, max_wh_ratio):
            ratio = min(max(float(max_wh_ratio), step), max_ratio)
            return original(img, math.ceil(ratio / step) * step)

        recognizer.resize_norm_img = bucketed

    @staticmethod
    def _pad_for_detection(image: np.ndarray, limit: int) -> np.ndarray:
        """Pad the page (white, right/bottom) to one of three square sizes so
        text detection always sees the same few input shapes.  Coordinates of
        detected text are unchanged because nothing moves."""
        h, w = image.shape[:2]
        side = max(h, w)
        buckets = (limit // 3, 2 * limit // 3, limit)
        # Pages larger than the limit become a square that PaddleOCR then
        # scales down to limit x limit - again the same shape every time.
        target = next((b for b in buckets if side <= b), side)
        if h == target and w == target:
            return image
        fill = 255 if image.ndim == 2 else (255,) * image.shape[2]
        import cv2
        return cv2.copyMakeBorder(image, 0, target - h, 0, target - w, cv2.BORDER_CONSTANT, value=fill)

    # ------------------------------------------------------------------ #
    # Recognition                                                          #
    # ------------------------------------------------------------------ #

    def recognize(self, image: np.ndarray, page: int = 1) -> list[dict[str, Any]]:
        """
        Run OCR on a single BGR image. Handles 2.x and 3.x result formats.

        Returns
        -------
        list[dict]  — each dict: {text, confidence, bbox, page}
        """
        if self._ocr is None:
            raise RuntimeError(
                "PaddleEngine.initialize() must be called before recognize()."
            )

        paddle_cfg = self._config.get("paddleocr", {})
        drop_score: float = paddle_cfg.get("drop_score", 0.5)
        if self._major_version < 3 and paddle_cfg.get("det_square_pad", True):
            image = self._pad_for_detection(image, int(paddle_cfg.get("text_det_limit_side_len", 960)))

        t0 = time.perf_counter()

        # ocr() parameter changed between versions
        try:
            if self._major_version >= 3:
                raw_result = self._ocr.ocr(image)
            else:
                raw_result = self._ocr.ocr(image, cls=True)
        except TypeError:
            # Fallback — try without cls
            raw_result = self._ocr.ocr(image)

        elapsed = time.perf_counter() - t0

        regions: list[dict[str, Any]] = []

        if raw_result is None:
            log.warning("PaddleOCR returned None for page %d", page)
            return regions

        for page_result in (raw_result or []):
            if page_result is None:
                continue

            # ----------------------------------------------------------------
            # PaddleOCR 3.x: OCRResult is a dict subclass with keys:
            #   rec_texts, rec_scores, dt_polys, rec_boxes, rec_polys
            # PaddleOCR 2.x: nested list  [ [bbox, (text, score)], ... ]
            # ----------------------------------------------------------------
            if isinstance(page_result, dict):
                # 3.x dict-based result (OCRResult inherits from dict)
                regions.extend(
                    self._parse_3x_result(page_result, page, drop_score)
                )
            elif isinstance(page_result, list):
                # 2.x nested list
                for line in page_result:
                    try:
                        bbox_raw, (text, confidence) = line
                        confidence = float(confidence)
                        if confidence < drop_score:
                            continue
                        regions.append({
                            "text":       str(text),
                            "confidence": round(confidence, 4),
                            "bbox":       self.bbox_to_list(bbox_raw),
                            "page":       page,
                        })
                    except (TypeError, ValueError, IndexError) as exc:
                        log.debug("Skipping malformed OCR line: %s -- %s", line, exc)
            else:
                log.debug("Unknown result element type: %s", type(page_result))

        # Natural reading order sort: page, line band (Y), then X
        regions = self.sort_reading_order(regions)

        log.info(
            "Page %d: %d region(s) detected in %.2fs",
            page, len(regions), elapsed,
        )
        return regions

    @staticmethod
    def sort_reading_order(regions: list[dict[str, Any]], line_tolerance: int = 15) -> list[dict[str, Any]]:
        """
        Sort regions in natural reading order (top-to-bottom, left-to-right).
        Groups boxes with similar Y coordinates into the same line.
        """
        if not regions:
            return regions

        def get_sort_key(r: dict[str, Any]) -> tuple:
            bbox = r.get("bbox", [0, 0, 0, 0])
            x1, y1, x2, y2 = bbox if len(bbox) == 4 else (0, 0, 0, 0)
            y_mid = (y1 + y2) / 2.0
            x_min = min(x1, x2)
            page = r.get("page", 1)
            line_idx = int(y_mid // line_tolerance)
            return (page, line_idx, x_min)

        return sorted(regions, key=get_sort_key)

    def _parse_3x_result(
        self, result: dict, page: int, drop_score: float
    ) -> list[dict[str, Any]]:
        """
        Parse a PaddleOCR 3.x OCRResult (dict subclass).

        Relevant keys:
            rec_texts  : list[str]
            rec_scores : list[float]
            dt_polys   : list[polygon] (or numpy array)
            rec_polys  : list[polygon]
            rec_boxes  : list[bbox]
        """
        regions: list[dict[str, Any]] = []

        raw_texts  = result.get("rec_texts")
        raw_scores = result.get("rec_scores")
        raw_polys  = result.get("dt_polys")
        if raw_polys is None:
            raw_polys = result.get("rec_polys")
        if raw_polys is None:
            raw_polys = result.get("rec_boxes")

        # Convert numpy arrays / iterables to Python lists safely
        texts = list(raw_texts) if raw_texts is not None else []
        scores = list(raw_scores) if raw_scores is not None else []
        polys = list(raw_polys) if raw_polys is not None else []

        for text, score, bbox_raw in zip(texts, scores, polys):
            try:
                score = float(score)
            except (ValueError, TypeError):
                score = 1.0

            if score < drop_score:
                continue

            regions.append({
                "text":       str(text),
                "confidence": round(score, 4),
                "bbox":       self.bbox_to_list(bbox_raw),
                "page":       page,
            })
        return regions


    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def is_ready(self) -> bool:
        return self._ocr is not None


# Alias for compatibility with api and external modules
PaddleOCREngine = PaddleEngine
