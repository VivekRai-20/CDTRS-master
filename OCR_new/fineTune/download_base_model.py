"""
fineTune/download_base_model.py
-------------------------------
Download the handwriting recognition base model ONCE (internet needed only for
this step).  After that, handwriting recognition and fine-tuning run offline.

The model is Microsoft TrOCR, a transformer trained on English handwriting.
It is the starting point that fineTune/training/train.py fine-tunes on your
own labelled handwriting.

Usage (from the OCR_new folder):

    python fineTune/download_base_model.py                 # trocr-small-handwritten (recommended, ~250 MB)
    python fineTune/download_base_model.py --model base    # trocr-base-handwritten (~1.3 GB, slower, a bit more accurate)
    python fineTune/download_base_model.py --no-activate   # download only, keep the current model active

Result:
    models/handwriting/trocr-small-handwritten/   the model files
    models/handwriting/active.txt                 name of the model the OCR uses

Uses only packages from requirements.txt (huggingface_hub, transformers, torch).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_OCR_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_OCR_ROOT))

MODELS = {
    "small": ("microsoft/trocr-small-handwritten", "trocr-small-handwritten"),
    "base": ("microsoft/trocr-base-handwritten", "trocr-base-handwritten"),
    "large": ("microsoft/trocr-large-handwritten", "trocr-large-handwritten"),
}

HANDWRITING_DIR = _OCR_ROOT / "models" / "handwriting"


def _files_to_download(repo_id: str) -> list[str]:
    from huggingface_hub import list_repo_files

    files = list_repo_files(repo_id)
    wanted = [
        f for f in files
        if "/" not in f and (f.endswith(".json") or f.endswith(".model") or f.endswith(".txt"))
    ]
    # One copy of the weights is enough: prefer safetensors.
    if "model.safetensors" in files:
        wanted.append("model.safetensors")
    elif "pytorch_model.bin" in files:
        wanted.append("pytorch_model.bin")
    else:
        raise RuntimeError(f"No model weights found in {repo_id}: {files}")
    return wanted


def verify(model_dir: Path) -> str:
    """Load the model from disk (offline) and read a blank line image."""
    import numpy as np
    from PIL import Image
    from ocr.handwriting_engine import load_trocr

    processor, model = load_trocr(model_dir, device="cpu")
    import torch

    image = Image.fromarray(np.full((64, 384, 3), 255, dtype=np.uint8))
    pixel_values = processor(images=image, return_tensors="pt").pixel_values
    with torch.no_grad():
        ids = model.generate(pixel_values, max_new_tokens=8)
    return processor.batch_decode(ids, skip_special_tokens=True)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the TrOCR handwriting base model.")
    parser.add_argument("--model", choices=sorted(MODELS), default="small",
                        help="small (default, fastest), base, or large")
    parser.add_argument("--no-activate", action="store_true",
                        help="do not make this the model the OCR uses")
    args = parser.parse_args()

    repo_id, folder_name = MODELS[args.model]
    dest = HANDWRITING_DIR / folder_name
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {repo_id}  ->  {dest}")
    from huggingface_hub import hf_hub_download

    for name in _files_to_download(repo_id):
        if (dest / name).exists():
            print(f"  = {name} (already there)")
            continue
        hf_hub_download(repo_id=repo_id, filename=name, local_dir=str(dest))
        print(f"  + {name}")

    meta = {
        "version": folder_name,
        "base_model": repo_id,
        "kind": "base",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "training_samples": 0,
        "metrics": {},
    }
    (dest / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("Checking that the model loads offline...")
    try:
        sample = verify(dest)
        print(f"  OK (blank test image read as {sample!r})")
    except Exception as exc:
        print(f"  [ERROR] The model could not be loaded: {exc}")
        sys.exit(1)

    active_file = HANDWRITING_DIR / "active.txt"
    if not args.no_activate:
        active_file.write_text(folder_name + "\n", encoding="utf-8")
        print(f"Active handwriting model: {folder_name}  (models/handwriting/active.txt)")
    elif not active_file.exists():
        print("Not activated. To use it:  echo " + folder_name + " > models/handwriting/active.txt")
    print("Done.")


if __name__ == "__main__":
    main()
