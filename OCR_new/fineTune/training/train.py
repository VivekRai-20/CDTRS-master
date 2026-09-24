"""
fineTune/training/train.py
---------------------------
Offline fine-tuning entry point.

This script orchestrates training for any supported model component.
All training runs completely offline using locally stored datasets and
base models.

Usage
-----
::

    python fineTune/training/train.py --config fineTune/configs/handwriting.yaml
    python fineTune/training/train.py --config fineTune/configs/text_type.yaml
    python fineTune/training/train.py --config fineTune/configs/classification.yaml

IMPORTANT: Do not modify the main system models during training.
           Export the trained model to fineTune/export/ first, then
           manually copy it to models/ after validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.logger import get_logger, setup_root_logger

setup_root_logger()
log = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline fine-tuning script for the OCR & Document Intelligence Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to a training configuration YAML file.",
    )
    parser.add_argument(
        "--component",
        choices=["handwriting", "text_type", "classification", "ner"],
        default=None,
        help="Override the component to train (optional; usually read from config).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="Override the number of training epochs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and dataset without running actual training.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    """Load training config from YAML."""
    if not config_path.exists():
        raise FileNotFoundError(f"Training config not found: {config_path}")
    import yaml
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def validate_dataset(dataset_dir: Path, component: str) -> None:
    """Check that the dataset directory exists and has samples."""
    if not dataset_dir.exists():
        raise FileNotFoundError(
            f"Dataset directory not found: {dataset_dir}\n"
            f"Please place training data in: {dataset_dir}"
        )
    files = list(dataset_dir.rglob("*"))
    image_files = [f for f in files if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".tiff")]
    log.info(
        "Dataset '%s': %d file(s), %d image(s).",
        dataset_dir, len(files), len(image_files),
    )


def train_text_type_classifier(config: dict) -> None:
    """
    Train a text-type detection classifier (PRINTED vs HANDWRITTEN).

    Uses scikit-learn with features extracted from image regions.
    """
    log.info("Training text-type classifier…")
    dataset_cfg = config.get("dataset", {})
    dataset_dir = Path(dataset_cfg.get("path", "fineTune/datasets/text_type"))
    validate_dataset(dataset_dir, "text_type")

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report
        import numpy as np
        import cv2
        import pickle

        from ocr.text_type_detector import _extract_features, TextType

        X, y = [], []

        for label_dir in [dataset_dir / "printed", dataset_dir / "handwritten"]:
            if not label_dir.exists():
                log.warning("Label directory missing: %s", label_dir)
                continue
            label = TextType.PRINTED.value if "printed" in label_dir.name else TextType.HANDWRITTEN.value
            for img_file in label_dir.glob("*.png"):
                img = cv2.imread(str(img_file))
                if img is None:
                    continue
                features = _extract_features(img)
                X.append(features)
                y.append(label)

        if not X:
            log.warning("No training samples found. Aborting.")
            return

        X_arr = np.array(X)
        y_arr = np.array(y)

        X_train, X_test, y_train, y_test = train_test_split(
            X_arr, y_arr, test_size=0.2, random_state=42, stratify=y_arr
        )

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        report = classification_report(y_test, model.predict(X_test))
        log.info("Evaluation:\n%s", report)

        # Export
        export_dir = Path(config.get("export", {}).get("path", "fineTune/export/text_type"))
        export_dir.mkdir(parents=True, exist_ok=True)
        model_file = export_dir / "classifier.pkl"
        with open(model_file, "wb") as fh:
            pickle.dump(model, fh)
        log.info("Model exported to '%s'.", model_file)

        # Save metadata
        meta = {
            "component":       "text_type",
            "algorithm":       "RandomForestClassifier",
            "training_samples": len(X_train),
            "test_samples":    len(X_test),
        }
        with open(export_dir / "model_meta.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    except ImportError:
        log.error("scikit-learn is required for text-type classifier training.")
        raise


def train_document_classifier(config: dict) -> None:
    """
    Train a document category classifier using TF-IDF + Logistic Regression.
    """
    log.info("Training document classifier…")
    dataset_cfg = config.get("dataset", {})
    dataset_dir = Path(dataset_cfg.get("path", "fineTune/datasets/classification"))
    validate_dataset(dataset_dir, "classification")

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder
        from sklearn.metrics import classification_report
        import pickle

        texts, labels = [], []
        for category_dir in dataset_dir.iterdir():
            if not category_dir.is_dir():
                continue
            for txt_file in category_dir.glob("*.txt"):
                text = txt_file.read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    texts.append(text)
                    labels.append(category_dir.name)

        if not texts:
            log.warning("No text samples found. Aborting.")
            return

        le = LabelEncoder()
        y = le.fit_transform(labels)
        X_train, X_test, y_train, y_test = train_test_split(
            texts, y, test_size=0.2, random_state=42
        )

        vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
        X_train_vec = vectorizer.fit_transform(X_train)
        X_test_vec = vectorizer.transform(X_test)

        model = LogisticRegression(max_iter=1000)
        model.fit(X_train_vec, y_train)

        report = classification_report(y_test, model.predict(X_test_vec), target_names=le.classes_)
        log.info("Evaluation:\n%s", report)

        export_dir = Path(config.get("export", {}).get("path", "fineTune/export/classification"))
        export_dir.mkdir(parents=True, exist_ok=True)

        for fname, obj in [
            ("classifier.pkl", model),
            ("vectorizer.pkl", vectorizer),
            ("label_encoder.pkl", le),
        ]:
            with open(export_dir / fname, "wb") as fh:
                pickle.dump(obj, fh)

        log.info("Classifier exported to '%s'.", export_dir)

    except ImportError:
        log.error("scikit-learn is required for document classifier training.")
        raise


_TRAINERS = {
    "text_type":      train_text_type_classifier,
    "classification": train_document_classifier,
}


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    component = args.component or config.get("component")
    if not component:
        log.error("No component specified. Use --component or set 'component' in config.")
        sys.exit(1)

    if args.epochs is not None:
        config.setdefault("training", {})["epochs"] = args.epochs

    log.info("=" * 60)
    log.info("OFFLINE FINE-TUNING")
    log.info("Component : %s", component)
    log.info("Config    : %s", args.config)
    log.info("Dry run   : %s", args.dry_run)
    log.info("=" * 60)

    if args.dry_run:
        log.info("Dry run mode — skipping actual training.")
        return

    trainer = _TRAINERS.get(component)
    if trainer is None:
        log.error(
            "No trainer available for component '%s'. "
            "Supported: %s", component, list(_TRAINERS.keys())
        )
        sys.exit(1)

    trainer(config)
    log.info("Training complete.")


if __name__ == "__main__":
    main()
