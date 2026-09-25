"""
fineTune/training/train.py
--------------------------
STEP 3 - train on your labelled lines (everything runs offline, on this PC).

From the OCR_new folder:

    python fineTune/training/train.py --task handwriting   # read handwriting better (TrOCR)
    python fineTune/training/train.py --task text_type     # tell handwriting from print better
    python fineTune/training/train.py --task classification  # optional: document categories

Settings come from fineTune/configs/<task>.yaml (epochs, learning rate, ...);
any of them can be overridden, e.g.  --epochs 20 --batch-size 4.

What each task produces
  handwriting     models/handwriting/vN/ (N = 1, 2, ...) + model_meta.json.
                  It becomes the active model (models/handwriting/active.txt)
                  only if it reads the TEST lines better than both the current
                  model and PaddleOCR - unless you pass --activate / --no-activate.
  text_type       models/classifiers/text_type/classifier.pkl (the previous one
                  is kept as classifier_<date>.pkl).  Installed only if it beats
                  the built-in model on the test lines (or with --activate).
  classification  models/classifiers/document/ (classifier, vectorizer, labels).

The test split (see labels.csv) is never used for training.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    CHECKPOINTS_DIR, CLASSIFICATION_DIR, CONFIGS_DIR, HANDWRITTEN, MODELS_DIR, PRINTED,
    classification_documents, error_rates, labelled_rows, line_image_path, load_config, load_ocr_config,
    next_version, read_labels, read_with_model, text_type_dataset,
)

HANDWRITING_DEFAULTS: dict[str, Any] = {
    "base_model": "",              # "" = the active model, else a folder under models/handwriting/
    "include_printed": False,      # also learn from PRINTED lines
    "epochs": 15,
    "batch_size": 8,
    "learning_rate": 3e-5,
    "weight_decay": 0.01,
    "warmup_ratio": 0.1,
    "max_target_length": 64,
    "augment": True,
    "early_stopping_patience": 4,
    "num_beams": 3,
    "freeze_encoder_epochs": 0,    # train only the decoder for the first N epochs
    "seed": 42,
    "device": "auto",              # auto = cuda if available, else cpu
    "min_train_lines": 20,
}
TEXT_TYPE_DEFAULTS: dict[str, Any] = {
    "n_estimators": 300,
    "max_depth": None,
    "min_lines_per_type": 20,
    "seed": 42,
}
CLASSIFICATION_DEFAULTS: dict[str, Any] = {
    "min_documents_per_category": 5,
    "max_features": 5000,
    "ngram_max": 2,
    "test_size": 0.2,
    "seed": 42,
}


def _log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Handwriting recognition (TrOCR)
# ──────────────────────────────────────────────────────────────────────────────

def _augment(image):
    """Small, realistic changes so the model does not memorise the scans:
    slight rotation / slant / scale, pen thickness, blur, contrast."""
    import cv2
    import numpy as np

    img = image
    h, w = img.shape[:2]
    if random.random() < 0.7:
        angle = random.uniform(-2.0, 2.0)
        shear = random.uniform(-0.15, 0.15)
        scale = random.uniform(0.9, 1.08)
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
        matrix[0, 1] += shear
        img = cv2.warpAffine(img, matrix, (w, h), borderValue=(255, 255, 255))
    if random.random() < 0.3:
        kernel = np.ones((2, 2), np.uint8)
        img = cv2.erode(img, kernel) if random.random() < 0.5 else cv2.dilate(img, kernel)
    if random.random() < 0.3:
        img = cv2.GaussianBlur(img, (0, 0), random.uniform(0.3, 1.0))
    if random.random() < 0.4:
        alpha, beta = random.uniform(0.8, 1.2), random.uniform(-20, 20)
        img = np.clip(img.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)
    return img


class _LineDataset:
    def __init__(self, rows: list[dict], processor, max_len: int, augment: bool) -> None:
        import cv2

        from ocr.handwriting_engine import prepare_line_image

        self.items = []
        for row in rows:
            image = cv2.imread(str(line_image_path(row)))
            if image is None:
                _log(f"  missing image, skipped: {row['image']}")
                continue
            self.items.append((prepare_line_image(image), row["text"].strip()))
        self.processor = processor
        self.max_len = max_len
        self.augment = augment

    def __len__(self) -> int:
        return len(self.items)

    def labels_for(self, text: str) -> list[int]:
        tok = self.processor.tokenizer
        ids = tok(text, add_special_tokens=True).input_ids
        # TrOCR generates after the decoder start token; the leading <s> that
        # the tokenizer adds is not part of what the model should produce.
        if ids and ids[0] in (tok.bos_token_id, tok.cls_token_id) and len(ids) > 1:
            ids = ids[1:]
        return ids[: self.max_len]

    def batch(self, indices: list[int]):
        import torch
        from PIL import Image

        images, labels = [], []
        for i in indices:
            image, text = self.items[i]
            if self.augment:
                image = _augment(image)
            images.append(Image.fromarray(image))
            labels.append(self.labels_for(text))
        pixel_values = self.processor(images=images, return_tensors="pt").pixel_values
        longest = max(len(l) for l in labels)
        label_tensor = torch.full((len(labels), longest), -100, dtype=torch.long)
        for row, ids in enumerate(labels):
            label_tensor[row, :len(ids)] = torch.tensor(ids, dtype=torch.long)
        return pixel_values, label_tensor


def _evaluate_model(model_dir: Path, rows: list[dict], device: str, num_beams: int) -> dict:
    import cv2

    from ocr.handwriting_engine import load_trocr, prepare_line_image

    processor, model = load_trocr(model_dir, device)
    images = [prepare_line_image(cv2.imread(str(line_image_path(r)))) for r in rows]
    hyps = read_with_model(model, processor, images, device, num_beams)
    return error_rates([r["text"] for r in rows], hyps)


def train_handwriting(cfg: dict, args: argparse.Namespace) -> None:
    import numpy as np
    import torch
    from transformers import get_linear_schedule_with_warmup

    from ocr.handwriting_engine import handwriting_root, load_trocr, resolve_model_dir

    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])
    device = cfg["device"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    ocr_cfg = load_ocr_config()
    root = handwriting_root(ocr_cfg)
    base_dir = resolve_model_dir(ocr_cfg, cfg["base_model"] or None)
    if base_dir is None:
        sys.exit("No handwriting model to start from.  Run once (needs internet):\n"
                 "    python fineTune/download_base_model.py")

    kinds = [HANDWRITTEN] + ([PRINTED] if cfg["include_printed"] else [])
    rows = read_labels()
    train_rows = labelled_rows(rows, kinds, "train")
    val_rows = labelled_rows(rows, kinds, "val")
    test_rows = labelled_rows(rows, [HANDWRITTEN], "test")
    _log(f"Lines: train {len(train_rows)}, val {len(val_rows)}, test {len(test_rows)} (handwritten)")
    if len(train_rows) < cfg["min_train_lines"]:
        sys.exit(f"Only {len(train_rows)} labelled training lines; label at least {cfg['min_train_lines']} "
                 "(python fineTune/label_tool.py).")
    if not val_rows:
        val_rows = train_rows[: max(1, len(train_rows) // 10)]
        _log("No validation lines yet - using a few training lines to pick the best epoch.")

    _log(f"Base model: {base_dir.name}   device: {device}")
    processor, model = load_trocr(base_dir, device)
    train_set = _LineDataset(train_rows, processor, cfg["max_target_length"], cfg["augment"])
    val_set = _LineDataset(val_rows, processor, cfg["max_target_length"], False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]),
                                  weight_decay=float(cfg["weight_decay"]))
    steps_per_epoch = math.ceil(len(train_set) / cfg["batch_size"])
    total_steps = steps_per_epoch * cfg["epochs"]
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * cfg["warmup_ratio"]), total_steps)

    run_dir = CHECKPOINTS_DIR / f"handwriting_{datetime.now():%Y%m%d_%H%M%S}"
    best_dir = run_dir / "best"
    run_dir.mkdir(parents=True, exist_ok=True)
    history = []
    best_cer, bad_epochs = float("inf"), 0

    base_val = error_rates([t for _, t in val_set.items],
                           read_with_model(model, processor, [i for i, _ in val_set.items], device, cfg["num_beams"]))
    _log(f"Before training: validation CER {base_val['cer']:.3f}  WER {base_val['wer']:.3f}")

    for epoch in range(1, cfg["epochs"] + 1):
        freeze = epoch <= cfg["freeze_encoder_epochs"]
        for p in model.encoder.parameters():
            p.requires_grad = not freeze
        model.train()
        order = list(range(len(train_set)))
        random.shuffle(order)
        started, total_loss = time.time(), 0.0
        for step in range(steps_per_epoch):
            indices = order[step * cfg["batch_size"]:(step + 1) * cfg["batch_size"]]
            if not indices:
                continue
            pixel_values, labels = train_set.batch(indices)
            loss = model(pixel_values=pixel_values.to(device), labels=labels.to(device)).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total_loss += loss.item()
        val_hyps = read_with_model(model, processor, [i for i, _ in val_set.items], device, cfg["num_beams"])
        val = error_rates([t for _, t in val_set.items], val_hyps)
        entry = {"epoch": epoch, "loss": round(total_loss / max(1, steps_per_epoch), 4),
                 "val_cer": val["cer"], "val_wer": val["wer"], "seconds": round(time.time() - started)}
        history.append(entry)
        _log(f"Epoch {epoch}/{cfg['epochs']}: loss {entry['loss']:.3f}  val CER {val['cer']:.3f}  "
             f"WER {val['wer']:.3f}  ({entry['seconds']}s)")
        if val["cer"] < best_cer:
            best_cer, bad_epochs = val["cer"], 0
            model.save_pretrained(best_dir)
            processor.save_pretrained(best_dir)
        else:
            bad_epochs += 1
            if bad_epochs >= cfg["early_stopping_patience"]:
                _log(f"No improvement for {bad_epochs} epochs - stopping early.")
                break

    if not best_dir.exists():
        sys.exit("Training produced no model.")

    # ── Compare on the TEST lines ─────────────────────────────────────────
    metrics: dict[str, Any] = {"validation_cer_before": base_val["cer"], "validation_cer_best": best_cer}
    new_test = old_test = paddle_test = None
    if test_rows:
        new_test = _evaluate_model(best_dir, test_rows, device, cfg["num_beams"])
        old_test = _evaluate_model(base_dir, test_rows, device, cfg["num_beams"])
        paddle_test = error_rates([r["text"] for r in test_rows], [r.get("ocr_text", "") for r in test_rows])
        metrics.update({"test_new": new_test, "test_previous": old_test, "test_paddleocr": paddle_test})
        _log(f"TEST lines ({len(test_rows)}):  new model CER {new_test['cer']:.3f}  |  "
             f"previous ({base_dir.name}) {old_test['cer']:.3f}  |  PaddleOCR {paddle_test['cer']:.3f}")
    else:
        _log("No handwritten TEST lines are labelled - cannot compare models; "
             "label some lines whose split is 'test'.")

    version = next_version(root)
    dest = root / version
    shutil.copytree(best_dir, dest)
    meta = {
        "version": version,
        "kind": "fine-tuned",
        "base_model": base_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "training_samples": len(train_set),
        "validation_samples": len(val_set),
        "test_samples": len(test_rows),
        "metrics": metrics,
        "history": history,
        "config": {k: v for k, v in cfg.items()},
    }
    (dest / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _log(f"Saved: {dest}")

    better = new_test is not None and new_test["cer"] < old_test["cer"] and new_test["cer"] <= paddle_test["cer"]
    if args.activate or (better and not args.no_activate):
        (root / "active.txt").write_text(version + "\n", encoding="utf-8")
        _log(f"ACTIVE handwriting model is now {version}.  Restart the CDTRS backend to use it.")
    else:
        reason = "--no-activate was given" if args.no_activate else (
            "it did not beat the current model and PaddleOCR on the test lines" if new_test else
            "there are no labelled test lines")
        _log(f"Not activated ({reason}).  To use it anyway:  echo {version} > models/handwriting/active.txt")


# ──────────────────────────────────────────────────────────────────────────────
# Printed / handwritten classifier
# ──────────────────────────────────────────────────────────────────────────────

def train_text_type(cfg: dict, args: argparse.Namespace) -> None:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    from ocr.text_type_detector import (
        FEATURE_NAMES, FEATURE_VERSION, _builtin_probability, default_model_path,
    )

    rows = read_labels()
    need = [HANDWRITTEN, PRINTED]
    train_rows = labelled_rows(rows, need, "train", need_text=False) + labelled_rows(rows, need, "val", need_text=False)
    test_rows = labelled_rows(rows, need, "test", need_text=False)
    X, y, _ = text_type_dataset(train_rows)
    Xt, yt, _ = text_type_dataset(test_rows)
    _log(f"Lines: train {len(y)} ({int(y.sum())} handwritten), test {len(yt)} ({int(yt.sum()) if len(yt) else 0} handwritten)")
    if len(y) == 0 or min(int(y.sum()), int((1 - y).sum())) < cfg["min_lines_per_type"]:
        sys.exit(f"Label at least {cfg['min_lines_per_type']} handwritten AND {cfg['min_lines_per_type']} "
                 "printed lines (type column) before training.")

    model = RandomForestClassifier(n_estimators=cfg["n_estimators"], max_depth=cfg["max_depth"],
                                   class_weight="balanced", random_state=cfg["seed"], n_jobs=-1)
    model.fit(X, y)

    metrics: dict[str, Any] = {}
    better = True
    if len(yt):
        pred = model.predict(Xt)
        builtin = np.array([1 if _builtin_probability(x) >= 0.5 else 0 for x in Xt])
        new_f1, old_f1 = f1_score(yt, pred, zero_division=0), f1_score(yt, builtin, zero_division=0)
        metrics = {"test_f1_new": round(float(new_f1), 4), "test_f1_builtin": round(float(old_f1), 4),
                   "confusion_new": confusion_matrix(yt, pred, labels=[0, 1]).tolist()}
        print(classification_report(yt, pred, labels=[0, 1], target_names=[PRINTED, HANDWRITTEN], zero_division=0))
        _log(f"TEST F1 (handwritten): new classifier {new_f1:.3f}  |  built-in model {old_f1:.3f}")
        better = new_f1 >= old_f1
    else:
        _log("No labelled TEST lines - the classifier cannot be compared with the built-in model.")

    if not (args.activate or (better and not args.no_activate)):
        _log("Not installed (it is not better than the built-in model). Use --activate to install anyway.")
        return
    path = default_model_path(load_ocr_config())
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"classifier_{datetime.now():%Y%m%d_%H%M%S}.pkl")
        path.rename(backup)
        _log(f"Previous classifier kept as {backup.name}")
    bundle = {"model": model, "features": FEATURE_NAMES, "labels": [PRINTED, HANDWRITTEN],
              "feature_version": FEATURE_VERSION, "metrics": metrics,
              "created_at": datetime.now().isoformat(timespec="seconds"), "training_samples": int(len(y))}
    with open(path, "wb") as fh:
        pickle.dump(bundle, fh)
    (path.parent / "model_meta.json").write_text(json.dumps(
        {k: v for k, v in bundle.items() if k != "model"}, indent=2), encoding="utf-8")
    _log(f"Installed {path}.  Restart the CDTRS backend to use it.")


# ──────────────────────────────────────────────────────────────────────────────
# Document categories (optional)
# ──────────────────────────────────────────────────────────────────────────────

def train_classification(cfg: dict, args: argparse.Namespace) -> None:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder

    if not CLASSIFICATION_DIR.exists() or not any(p.is_dir() for p in CLASSIFICATION_DIR.iterdir()):
        sys.exit(f"Put documents into {CLASSIFICATION_DIR}/<CATEGORY>/ (one folder per category).")
    _log("Reading documents (scans are OCR'd once and cached as <name>.ocr.txt) ...")
    texts, labels = classification_documents(CLASSIFICATION_DIR)
    counts = {label: labels.count(label) for label in sorted(set(labels))}
    _log(f"Documents per category: {counts}")
    if len(counts) < 2 or min(counts.values()) < cfg["min_documents_per_category"]:
        sys.exit(f"Need at least {cfg['min_documents_per_category']} documents in each of two or more "
                 "category folders.")
    encoder = LabelEncoder()
    y = encoder.fit_transform(labels)
    X_train, X_test, y_train, y_test = train_test_split(
        texts, y, test_size=cfg["test_size"], random_state=cfg["seed"], stratify=y)
    vectorizer = TfidfVectorizer(max_features=cfg["max_features"], ngram_range=(1, cfg["ngram_max"]))
    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(vectorizer.fit_transform(X_train), y_train)
    print(classification_report(y_test, model.predict(vectorizer.transform(X_test)),
                                labels=list(range(len(encoder.classes_))), target_names=list(encoder.classes_),
                                zero_division=0))
    # The numbers above come from documents held back; the installed model
    # then learns from all of them.
    vectorizer = TfidfVectorizer(max_features=cfg["max_features"], ngram_range=(1, cfg["ngram_max"]))
    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(vectorizer.fit_transform(texts), y)
    dest = MODELS_DIR / "classifiers" / "document"
    dest.mkdir(parents=True, exist_ok=True)
    for name, obj in (("classifier.pkl", model), ("vectorizer.pkl", vectorizer), ("label_encoder.pkl", encoder)):
        with open(dest / name, "wb") as fh:
            pickle.dump(obj, fh)
    (dest / "model_meta.json").write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "categories": list(encoder.classes_), "documents": len(texts)}, indent=2), encoding="utf-8")
    _log(f"Installed document classifier in {dest}")


# ──────────────────────────────────────────────────────────────────────────────

TASKS = {
    "handwriting": (train_handwriting, HANDWRITING_DEFAULTS),
    "text_type": (train_text_type, TEXT_TYPE_DEFAULTS),
    "classification": (train_classification, CLASSIFICATION_DEFAULTS),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", required=True, choices=sorted(TASKS))
    parser.add_argument("--config", type=Path, default=None,
                        help="settings file (default fineTune/configs/<task>.yaml)")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--base-model", help="handwriting: model folder to start from")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--activate", action="store_true", help="always use the new model")
    group.add_argument("--no-activate", action="store_true", help="never switch to the new model")
    args = parser.parse_args()

    trainer, defaults = TASKS[args.task]
    cfg = load_config(args.config or CONFIGS_DIR / f"{args.task}.yaml", defaults)
    for key in ("epochs", "batch_size", "learning_rate", "base_model"):
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = value
    _log(f"Task {args.task}: " + ", ".join(f"{k}={v}" for k, v in cfg.items()))
    trainer(cfg, args)


if __name__ == "__main__":
    main()
