"""
fineTune/evaluation/evaluate.py
--------------------------------
Offline evaluation script for fine-tuned models.

Computes the appropriate metrics for each component type:

  OCR / Handwriting  → CER, WER
  Text-Type          → Accuracy, Precision, Recall, F1, Confusion Matrix
  Classification     → Accuracy, Precision, Recall, F1, Confusion Matrix
  NER                → Entity Precision, Recall, F1

Usage
-----
::

    python fineTune/evaluation/evaluate.py \\
        --model fineTune/export/text_type/ \\
        --dataset fineTune/datasets/text_type/ \\
        --component text_type

Results are printed to stdout and saved as ``evaluation_results.json``
in the model directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.logger import get_logger, setup_root_logger

setup_root_logger()
log = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a fine-tuned model component offline.",
    )
    parser.add_argument("--model", required=True, type=Path, help="Path to the model directory.")
    parser.add_argument("--dataset", required=True, type=Path, help="Path to the evaluation dataset.")
    parser.add_argument(
        "--component",
        required=True,
        choices=["text_type", "classification", "ocr", "handwriting", "ner"],
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Path to write evaluation_results.json (default: model dir).",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Metric helpers
# ──────────────────────────────────────────────────────────────────────────────

def compute_cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate using edit distance."""
    import editdistance  # type: ignore
    if not reference:
        return 1.0 if hypothesis else 0.0
    return editdistance.eval(reference, hypothesis) / len(reference)


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate."""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    try:
        import editdistance
        return editdistance.eval(ref_words, hyp_words) / len(ref_words)
    except ImportError:
        # Naive implementation
        errors = sum(1 for r, h in zip(ref_words, hyp_words) if r != h)
        errors += abs(len(ref_words) - len(hyp_words))
        return errors / len(ref_words)


def evaluate_classification(model_dir: Path, dataset_dir: Path) -> dict:
    """Evaluate a document / text-type classifier."""
    try:
        import pickle
        import numpy as np
        from sklearn.metrics import (
            accuracy_score, precision_recall_fscore_support,
            confusion_matrix, classification_report,
        )
        import cv2

        from ocr.text_type_detector import _extract_features, TextType

        model_file = model_dir / "classifier.pkl"
        if not model_file.exists():
            raise FileNotFoundError(f"Model not found: {model_file}")

        with open(model_file, "rb") as fh:
            model = pickle.load(fh)

        X, y_true = [], []
        for label_dir in dataset_dir.iterdir():
            if not label_dir.is_dir():
                continue
            for img_file in label_dir.glob("*.png"):
                img = cv2.imread(str(img_file))
                if img is None:
                    continue
                X.append(_extract_features(img))
                y_true.append(label_dir.name)

        if not X:
            return {"error": "No evaluation samples found."}

        X_arr = np.array(X)
        y_pred = model.predict(X_arr)

        report = classification_report(y_true, y_pred, output_dict=True)
        cm = confusion_matrix(y_true, y_pred, labels=sorted(set(y_true))).tolist()

        return {
            "accuracy":        report.get("accuracy", 0.0),
            "macro_f1":        report.get("macro avg", {}).get("f1-score", 0.0),
            "confusion_matrix": cm,
            "per_class":       {
                k: v for k, v in report.items()
                if isinstance(v, dict)
            },
        }

    except ImportError as exc:
        return {"error": f"Missing dependency: {exc}"}


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    log.info("=" * 60)
    log.info("OFFLINE EVALUATION")
    log.info("Component : %s", args.component)
    log.info("Model     : %s", args.model)
    log.info("Dataset   : %s", args.dataset)
    log.info("=" * 60)

    results: dict = {}

    if args.component in ("text_type", "classification"):
        results = evaluate_classification(args.model, args.dataset)
    elif args.component in ("ocr", "handwriting"):
        log.warning(
            "OCR/handwriting evaluation requires matched image-transcription pairs. "
            "Implement for your specific dataset format."
        )
        results = {"message": "OCR evaluation not yet implemented in this script."}
    elif args.component == "ner":
        log.warning("NER evaluation requires annotated entity spans.")
        results = {"message": "NER evaluation not yet implemented in this script."}

    # Print results
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2))

    # Save results
    output_dir = args.output or args.model
    output_dir.mkdir(parents=True, exist_ok=True)
    result_file = output_dir / "evaluation_results.json"
    with open(result_file, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    log.info("Results saved to '%s'.", result_file)


if __name__ == "__main__":
    main()
