"""
fineTune/evaluation/evaluate.py
-------------------------------
STEP 4 - measure how well the models read your labelled lines.

From the OCR_new folder:

    python fineTune/evaluation/evaluate.py                       # handwriting, test lines
    python fineTune/evaluation/evaluate.py --task text_type      # printed / handwritten detection
    python fineTune/evaluation/evaluate.py --task classification # document categories

Handwriting options
    --split test|val|train|all   which labelled lines to use (default test)
    --models v1 v2 ...           only these model folders (default: all installed)
    --show 10                    also list the 10 worst-read lines
    --report                     save the numbers to fineTune/evaluation/reports/

CER = character error rate, WER = word error rate (0.00 = perfect,
0.10 = one character in ten is wrong).  PaddleOCR's own reading (the
ocr_text column) is shown for comparison.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402
    CLASSIFICATION_DIR, FINETUNE_DIR, HANDWRITTEN, MODELS_DIR, PRINTED, classification_documents, distance,
    error_rates, labelled_rows, line_image_path, load_ocr_config, normalise_text, ocr_confidence, read_labels,
    read_with_model, text_type_dataset,
)

REPORTS_DIR = FINETUNE_DIR / "evaluation" / "reports"


def _rows_for(split: str, kinds: list[str], need_text: bool = True) -> list[dict]:
    rows = read_labels()
    if split == "all":
        return labelled_rows(rows, kinds, None, need_text)
    return labelled_rows(rows, kinds, split, need_text)


def _save_report(task: str, data: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{task}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved: {path}")


# ──────────────────────────────────────────────────────────────────────────────

def evaluate_handwriting(args: argparse.Namespace) -> None:
    import cv2
    import torch

    from ocr.handwriting_engine import handwriting_root, list_models, load_trocr, prepare_line_image, resolve_model_dir

    config = load_ocr_config()
    rows = _rows_for(args.split, [HANDWRITTEN])
    if not rows:
        sys.exit(f"No labelled HANDWRITTEN lines in the '{args.split}' split.  "
                 "Label some with  python fineTune/label_tool.py  (or use --split all).")
    refs = [r["text"] for r in rows]
    images = [prepare_line_image(cv2.imread(str(line_image_path(r)))) for r in rows]

    root = handwriting_root(config)
    models = [root / m for m in args.models] if args.models else list_models(config)
    active = resolve_model_dir(config)
    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else (
        "cpu" if args.device == "auto" else args.device)
    num_beams = int((config.get("handwriting") or {}).get("num_beams", 3))

    results = {"PaddleOCR": (error_rates(refs, [r.get("ocr_text", "") for r in rows]),
                             [r.get("ocr_text", "") for r in rows])}
    for folder in models:
        if not folder.is_dir():
            print(f"  (skipped {folder.name}: not found)")
            continue
        print(f"  reading {len(rows)} line(s) with {folder.name} ...", flush=True)
        processor, model = load_trocr(folder, device)
        hyps = read_with_model(model, processor, images, device, num_beams)
        results[folder.name] = (error_rates(refs, hyps), hyps)
        del model

    print(f"\nHandwritten lines, split '{args.split}': {len(rows)}\n")
    print(f"  {'Reader':32s} {'CER':>7s} {'WER':>7s}")
    print(f"  {'-' * 32} {'-' * 7} {'-' * 7}")
    best = min(results, key=lambda k: results[k][0]["cer"])
    for name, (scores, _) in results.items():
        tags = []
        if active is not None and name == active.name:
            tags.append("ACTIVE")
        if name == best:
            tags.append("best")
        print(f"  {name:32s} {scores['cer']:7.3f} {scores['wer']:7.3f}  {' '.join(tags)}")

    if args.show:
        name = active.name if active is not None and active.name in results else best
        hyps = results[name][1]
        scored = sorted(
            ((distance(list(normalise_text(r)), list(normalise_text(h))) / max(1, len(normalise_text(r))), row, h)
             for row, r, h in zip(rows, refs, hyps)), key=lambda t: -t[0])
        print(f"\nWorst {args.show} line(s) for {name}:")
        for err, row, hyp in scored[: args.show]:
            print(f"  [{err:4.2f}] {row['image']}\n         correct: {row['text']}\n"
                  f"         read   : {hyp}\n         Paddle : {row.get('ocr_text', '')}")

    if args.report:
        _save_report("handwriting", {
            "split": args.split, "lines": len(rows), "active": active.name if active else None,
            "results": {k: v[0] for k, v in results.items()},
        })


# ──────────────────────────────────────────────────────────────────────────────

def evaluate_text_type(args: argparse.Namespace) -> None:
    import cv2

    from ocr.text_type_detector import TextTypeDetector

    rows = _rows_for(args.split, [HANDWRITTEN, PRINTED], need_text=False)
    _, y, kept = text_type_dataset(rows)
    if not len(y):
        sys.exit(f"No labelled HANDWRITTEN/PRINTED lines in the '{args.split}' split (try --split all).")
    detector = TextTypeDetector(load_ocr_config())
    predictions = [detector.detect(cv2.imread(str(line_image_path(row))), ocr_confidence(row))["text_type"]
                   for row in kept]
    truth = [HANDWRITTEN if v == 1 else PRINTED for v in y]

    print(f"\nPrinted / handwritten detection ({detector.source}), split '{args.split}': {len(truth)} lines\n")
    print(f"  {'actual / detected':20s} {'HANDWRITTEN':>12s} {'PRINTED':>9s} {'UNKNOWN':>9s}")
    matrix = {}
    for actual in (HANDWRITTEN, PRINTED):
        counts = [sum(1 for t, p in zip(truth, predictions) if t == actual and p == pred)
                  for pred in (HANDWRITTEN, PRINTED, "UNKNOWN")]
        matrix[actual] = counts
        print(f"  {actual:20s} {counts[0]:12d} {counts[1]:9d} {counts[2]:9d}")
    decided = [(t, p) for t, p in zip(truth, predictions) if p != "UNKNOWN"]
    accuracy = sum(t == p for t, p in decided) / len(decided) if decided else 0.0
    unknown = 1 - len(decided) / len(truth)
    printed_as_hw = matrix[PRINTED][0] / max(1, sum(matrix[PRINTED]))
    print(f"\n  accuracy on decided lines : {accuracy:.3f}")
    print(f"  left UNKNOWN              : {unknown:.1%}")
    print(f"  printed lines called handwritten: {printed_as_hw:.1%}  (these would be re-read by the handwriting model)")
    if args.report:
        _save_report("text_type", {"split": args.split, "lines": len(truth), "source": detector.source,
                                   "matrix": matrix, "accuracy": accuracy, "unknown": unknown})


# ──────────────────────────────────────────────────────────────────────────────

def evaluate_classification(args: argparse.Namespace) -> None:
    from sklearn.metrics import classification_report

    folder = MODELS_DIR / "classifiers" / "document"
    try:
        with open(folder / "classifier.pkl", "rb") as fh:
            model = pickle.load(fh)
        with open(folder / "vectorizer.pkl", "rb") as fh:
            vectorizer = pickle.load(fh)
        with open(folder / "label_encoder.pkl", "rb") as fh:
            encoder = pickle.load(fh)
    except FileNotFoundError:
        sys.exit("No document classifier yet - run  python fineTune/training/train.py --task classification")
    source = Path(args.folder) if args.folder else CLASSIFICATION_DIR
    texts, labels = classification_documents(source)
    known = [i for i, label in enumerate(labels) if label in set(encoder.classes_)]
    if not known:
        sys.exit(f"No documents in {source} for the categories {list(encoder.classes_)}.")
    print("Note: documents that were used for training score higher than new ones;"
          " use --folder with documents the model has not seen for a fair check.\n")
    y = encoder.transform([labels[i] for i in known])
    pred = model.predict(vectorizer.transform([texts[i] for i in known]))
    print(classification_report(y, pred, labels=list(range(len(encoder.classes_))),
                                target_names=list(encoder.classes_), zero_division=0))


# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", default="handwriting", choices=["handwriting", "text_type", "classification"])
    parser.add_argument("--split", default="test", choices=["test", "val", "train", "all"])
    parser.add_argument("--models", nargs="*", help="handwriting model folders to compare (default: all)")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--show", type=int, default=0, help="list the N worst-read lines")
    parser.add_argument("--folder", help="classification: folder with <CATEGORY>/ sub-folders")
    parser.add_argument("--report", action="store_true", help="save a JSON report")
    args = parser.parse_args()
    {"handwriting": evaluate_handwriting, "text_type": evaluate_text_type,
     "classification": evaluate_classification}[args.task](args)


if __name__ == "__main__":
    main()
