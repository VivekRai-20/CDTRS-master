"""
fineTune/set_active_model.py
----------------------------
See the installed handwriting models and choose the one CDTRS uses.

From the OCR_new folder:

    python fineTune/set_active_model.py            # list models and their scores
    python fineTune/set_active_model.py v2         # use v2
    python fineTune/set_active_model.py trocr-small-handwritten   # back to the base model
    python fineTune/set_active_model.py --off      # no handwriting model (PaddleOCR only)

Restart the CDTRS backend afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_ocr_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", nargs="?", help="model folder name under models/handwriting/")
    parser.add_argument("--off", action="store_true", help="do not use a handwriting model")
    args = parser.parse_args()

    from ocr.handwriting_engine import handwriting_root, list_models, resolve_model_dir

    config = load_ocr_config()
    root = handwriting_root(config)
    active_file = root / "active.txt"

    if args.off:
        active_file.write_text("\n", encoding="utf-8")
        print("Handwriting model switched off.  Restart the CDTRS backend.")
        return
    if args.model:
        if resolve_model_dir(config, args.model) is None:
            sys.exit(f"'{args.model}' is not a model folder in {root}.  Run without arguments to list them.")
        active_file.write_text(args.model + "\n", encoding="utf-8")
        print(f"Active handwriting model: {args.model}.  Restart the CDTRS backend to use it.")
        return

    active = resolve_model_dir(config)
    models = list_models(config)
    if not models:
        print(f"No handwriting models in {root}.  Run  python fineTune/download_base_model.py")
        return
    print(f"Handwriting models in {root}:\n")
    print(f"  {'':2s}{'model':28s} {'created':20s} {'lines':>6s} {'test CER':>9s} {'Paddle CER':>11s}")
    for folder in models:
        meta = {}
        meta_file = folder / "model_meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except ValueError:
                pass
        metrics = meta.get("metrics") or {}
        test = (metrics.get("test_new") or {}).get("cer")
        paddle = (metrics.get("test_paddleocr") or {}).get("cer")
        mark = "* " if active is not None and folder == active else "  "
        print(f"  {mark}{folder.name:28s} {str(meta.get('created_at', meta.get('downloaded_at', '')))[:19]:20s} "
              f"{str(meta.get('training_samples', '-')):>6s} "
              f"{('%.3f' % test) if test is not None else '-':>9s} {('%.3f' % paddle) if paddle is not None else '-':>11s}")
    print("\n  * = active.  Compare them on the same lines with:  python fineTune/evaluation/evaluate.py")


if __name__ == "__main__":
    main()
