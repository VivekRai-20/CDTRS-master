"""
fineTune/common.py
------------------
Shared helpers for the fine-tuning tools: folder layout, the labels.csv
file, dataset splits and error rates.

Folder layout (all under OCR_new/fineTune/)::

    datasets/raw/          your handwriting scans / photos / PDFs (any sub-folders)
    datasets/lines/        one image per text line, made by prepare_dataset.py
    datasets/labels.csv    one row per line image - you fill in "text" and "type"
    datasets/classification/<CATEGORY>/   documents for the document classifier
    checkpoints/           training runs (safe to delete)
    configs/               training settings (*.yaml)

Only packages from requirements.txt are used.
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

FINETUNE_DIR = Path(__file__).resolve().parent
OCR_ROOT = FINETUNE_DIR.parent
if str(OCR_ROOT) not in sys.path:
    sys.path.insert(0, str(OCR_ROOT))

DATASETS_DIR = FINETUNE_DIR / "datasets"
RAW_DIR = DATASETS_DIR / "raw"
LINES_DIR = DATASETS_DIR / "lines"
LABELS_CSV = DATASETS_DIR / "labels.csv"
CLASSIFICATION_DIR = DATASETS_DIR / "classification"
CHECKPOINTS_DIR = FINETUNE_DIR / "checkpoints"
CONFIGS_DIR = FINETUNE_DIR / "configs"
MODELS_DIR = OCR_ROOT / "models"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DOCUMENT_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}

# Values of the "type" column.
HANDWRITTEN = "HANDWRITTEN"
PRINTED = "PRINTED"
SKIP = "SKIP"
TYPES = (HANDWRITTEN, PRINTED, SKIP)

COLUMNS = [
    "image",            # path under datasets/lines/
    "source",           # original file (relative to datasets/raw/)
    "page",
    "bbox",             # x1 y1 x2 y2 on the page image
    "ocr_text",         # what PaddleOCR read (kept for comparison)
    "ocr_confidence",
    "predicted_type",   # what the text-type detector guessed
    "text",             # CORRECT text - filled in by you
    "type",             # HANDWRITTEN / PRINTED / SKIP - filled in by you
    "split",            # train / val / test (assigned automatically, editable)
    "labelled_at",
]


# ──────────────────────────────────────────────────────────────────────────────
# labels.csv
# ──────────────────────────────────────────────────────────────────────────────

def read_labels(path: Path = LABELS_CSV) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for column in COLUMNS:
            row.setdefault(column, "")
            if row[column] is None:
                row[column] = ""
    return rows


def write_labels(rows: Iterable[dict[str, Any]], path: Path = LABELS_CSV) -> None:
    """Write atomically (a crash never leaves a half-written file).
    UTF-8 with BOM so Excel shows non-English characters correctly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="labels_", suffix=".csv", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in COLUMNS})
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def assign_split(image_name: str, val: float = 0.1, test: float = 0.1) -> str:
    """Stable train/val/test split from the file name (never changes between
    runs, so test lines are never used for training)."""
    bucket = int(hashlib.sha1(image_name.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    if bucket < test:
        return "test"
    if bucket < test + val:
        return "val"
    return "train"


def is_labelled(row: dict[str, str]) -> bool:
    kind = (row.get("type") or "").strip().upper()
    if kind == SKIP:
        return True
    return kind in (HANDWRITTEN, PRINTED) and bool((row.get("text") or "").strip())


def labelled_rows(rows: list[dict[str, str]], kinds: Iterable[str], split: Optional[str] = None,
                  need_text: bool = True) -> list[dict[str, str]]:
    kinds = {k.upper() for k in kinds}
    result = []
    for row in rows:
        kind = (row.get("type") or "").strip().upper()
        if kind not in kinds:
            continue
        if need_text and not (row.get("text") or "").strip():
            continue
        if split and (row.get("split") or "train") != split:
            continue
        result.append(row)
    return result


def line_image_path(row: dict[str, str]) -> Path:
    return LINES_DIR / row["image"]


def summary(rows: list[dict[str, str]]) -> str:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        kind = (row.get("type") or "").strip().upper() or "UNLABELLED"
        if kind in (HANDWRITTEN, PRINTED) and not (row.get("text") or "").strip():
            kind = kind + " (no text yet)"
        split = row.get("split") or "train"
        counts.setdefault(kind, {}).setdefault(split, 0)
        counts[kind][split] += 1
    lines = [f"{len(rows)} line image(s) in {LABELS_CSV}"]
    for kind in sorted(counts):
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(counts[kind].items()))
        lines.append(f"  {kind:28s} {sum(counts[kind].values()):5d}   ({parts})")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Error rates
# ──────────────────────────────────────────────────────────────────────────────

def distance(a: list, b: list) -> int:
    """Edit distance between two sequences."""
    try:
        import editdistance  # requirements.txt
        return int(editdistance.eval(a, b))
    except Exception:
        previous = list(range(len(b) + 1))
        for i, x in enumerate(a, 1):
            current = [i]
            for j, y in enumerate(b, 1):
                current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
            previous = current
        return previous[-1]


def normalise_text(text: str) -> str:
    return " ".join((text or "").split())


def error_rates(references: list[str], hypotheses: list[str]) -> dict[str, float]:
    """Character and word error rate over a set of lines (0 = perfect)."""
    char_errors = char_total = word_errors = word_total = 0
    for ref, hyp in zip(references, hypotheses):
        ref, hyp = normalise_text(ref), normalise_text(hyp)
        char_errors += distance(list(ref), list(hyp))
        char_total += max(1, len(ref))
        word_errors += distance(ref.split(), hyp.split())
        word_total += max(1, len(ref.split()))
    return {
        "cer": round(char_errors / char_total, 4) if char_total else 0.0,
        "wer": round(word_errors / word_total, 4) if word_total else 0.0,
        "lines": len(references),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Shared by training and evaluation
# ──────────────────────────────────────────────────────────────────────────────

def read_with_model(model, processor, images: list, device: str, num_beams: int, batch_size: int = 8) -> list[str]:
    """Read prepared line images (see ocr.handwriting_engine.prepare_line_image)
    with a TrOCR model."""
    import torch
    from PIL import Image

    out: list[str] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(images), batch_size):
            chunk = [Image.fromarray(img) for img in images[start:start + batch_size]]
            pixel_values = processor(images=chunk, return_tensors="pt").pixel_values.to(device)
            ids = model.generate(pixel_values, num_beams=num_beams, max_new_tokens=64)
            out.extend(t.strip() for t in processor.batch_decode(ids, skip_special_tokens=True))
    return out


def ocr_confidence(row: dict[str, str]) -> Optional[float]:
    try:
        value = row.get("ocr_confidence")
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def text_type_dataset(rows: list[dict[str, str]]):
    """Feature matrix X, labels y (1 = handwritten) and the rows used."""
    import cv2
    import numpy as np

    from ocr.text_type_detector import extract_features

    X, y, kept = [], [], []
    for row in rows:
        image = cv2.imread(str(line_image_path(row)))
        if image is None:
            continue
        features = extract_features(image, ocr_confidence(row))
        if features is None:
            continue
        X.append(features)
        y.append(1 if row["type"].upper() == HANDWRITTEN else 0)
        kept.append(row)
    return (np.stack(X) if X else np.zeros((0, 1))), np.array(y, dtype=int), kept


CLASSIFIABLE_EXTENSIONS = {".txt", ".pdf", ".docx"} | IMAGE_EXTENSIONS


def document_text(path: Path, processor=None) -> str:
    """Text of a document for the document classifier; OCR results are cached
    next to the file as <name>.ocr.txt so a second run is fast."""
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    cache = path.with_name(path.name + ".ocr.txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")
    if processor is None:
        from document_intelligence import DocumentProcessor
        processor = DocumentProcessor()
    text = processor.process(path, mode="ocr").full_text
    cache.write_text(text, encoding="utf-8")
    return text


def classification_documents(folder: Path, processor=None) -> tuple[list[str], list[str]]:
    """(texts, labels) from folder/<CATEGORY>/<documents>."""
    texts, labels = [], []
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        for path in sorted(sub.rglob("*")):
            if not path.is_file() or path.name.endswith(".ocr.txt") or \
                    path.suffix.lower() not in CLASSIFIABLE_EXTENSIONS:
                continue
            if processor is None and path.suffix.lower() != ".txt" and \
                    not path.with_name(path.name + ".ocr.txt").exists():
                from document_intelligence import DocumentProcessor
                processor = DocumentProcessor()
            print(f"  {sub.name}/{path.name}", flush=True)
            text = document_text(path, processor)
            if text.strip():
                texts.append(text)
                labels.append(sub.name)
    return texts, labels


# ──────────────────────────────────────────────────────────────────────────────
# Misc
# ──────────────────────────────────────────────────────────────────────────────

def load_config(path: Optional[Path], defaults: dict[str, Any]) -> dict[str, Any]:
    """Defaults, overridden by a YAML config file when given / present."""
    import yaml

    config = dict(defaults)
    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as fh:
            config.update(yaml.safe_load(fh) or {})
    return config


def load_ocr_config() -> dict[str, Any]:
    import yaml

    with open(OCR_ROOT / "config" / "config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def next_version(folder: Path) -> str:
    """v1, v2, ... - the first version name not used in *folder*."""
    used = {p.name for p in folder.iterdir()} if folder.exists() else set()
    n = 1
    while f"v{n}" in used:
        n += 1
    return f"v{n}"
