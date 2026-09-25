"""
setup_models.py
---------------
One-time setup: put the PaddleOCR models inside this project so the OCR runs
fully offline, on any PC, without looking in the Windows user profile.

Usage (run once, from the OCR_new folder, while the PC has internet the first
time — after that it works offline):

    python setup_models.py            # copy the models into models/paddleocr/
    python setup_models.py --check    # only show what is installed

What it does
    1. Starts PaddleOCR 2.8.1 once with the settings in config/config.yaml.
       PaddleOCR downloads its PP-OCRv4 models into ~/.paddleocr/whl/ the
       first time (skipped when they are already there).
    2. Copies exactly those three models into
           models/paddleocr/det/   text detection
           models/paddleocr/rec/   text recognition
           models/paddleocr/cls/   text-line orientation
       and writes models/paddleocr/model_info.json (which model is where).

The OCR engine (ocr/paddle_engine.py) uses models/paddleocr/* whenever they
contain a model, so after this the ~/.paddleocr cache is no longer needed.

Only the pinned PaddleOCR 2.x package is supported (see requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import yaml

MODEL_FILES = ("inference.pdmodel", "inference.pdiparams", "inference.pdiparams.info")
ROLES = ("det", "rec", "cls")


def _load_config() -> dict:
    with open(_ROOT / "config" / "config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _abs(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else _ROOT / p


def _has_model(folder: Path) -> bool:
    return folder.is_dir() and (folder / "inference.pdmodel").exists() and (folder / "inference.pdiparams").exists()


def _local_dirs(paddle_cfg: dict) -> dict[str, Path]:
    return {
        role: _abs(paddle_cfg.get(f"{role}_model_dir", f"models/paddleocr/{role}"))
        for role in ROLES
    }


def _cache_dirs(lang: str, ocr_version: str) -> dict[str, tuple[Path, str]]:
    """Where PaddleOCR 2.x keeps (or downloads) each model: {role: (dir, url)}."""
    from paddleocr.paddleocr import BASE_DIR, confirm_model_dir_url, get_model_config

    result = {}
    for role in ROLES:
        model_lang = "ch" if role == "cls" else lang
        cfg = get_model_config("OCR", ocr_version, role, model_lang)
        default = Path(BASE_DIR) / "whl" / role / (model_lang if role != "cls" else "")
        folder, url = confirm_model_dir_url(None, str(default), cfg["url"])
        result[role] = (Path(folder), url)
    return result


def show_status(local: dict[str, Path]) -> bool:
    ok = True
    for role, folder in local.items():
        state = "OK" if _has_model(folder) else "MISSING"
        ok &= state == "OK"
        print(f"  [{state:7s}] {role.upper()}: {folder}")
    info = local["det"].parent / "model_info.json"
    if info.exists():
        print(f"  model_info.json: {info.read_text(encoding='utf-8').strip()[:400]}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report what is installed")
    args = parser.parse_args()

    config = _load_config()
    paddle_cfg = config.get("paddleocr", {})
    lang = paddle_cfg.get("lang", "en")
    ocr_version = paddle_cfg.get("ocr_version", "PP-OCRv4")
    local = _local_dirs(paddle_cfg)

    print("=" * 60)
    print("  PaddleOCR model setup")
    print("=" * 60)

    if args.check:
        sys.exit(0 if show_status(local) else 1)

    try:
        import paddleocr as _poc
    except ImportError:
        print("[ERROR] paddleocr is not installed (see requirements.txt).")
        sys.exit(1)
    version = getattr(_poc, "__version__", "0")
    if int(version.split(".")[0]) >= 3:
        print(f"[ERROR] PaddleOCR {version} is installed, but this project uses PaddleOCR 2.8.1.")
        sys.exit(1)
    if ocr_version not in ("PP-OCR", "PP-OCRv2", "PP-OCRv3", "PP-OCRv4"):
        ocr_version = "PP-OCRv4"

    print(f"PaddleOCR {version}, models {ocr_version}, language '{lang}'\n")

    # 1. Make sure the models are in PaddleOCR's own cache (downloads once).
    cache = _cache_dirs(lang, ocr_version)
    if not all(_has_model(folder) for folder, _ in cache.values()):
        print("Downloading the PaddleOCR models (first time only)...")
        from paddleocr import PaddleOCR
        PaddleOCR(lang=lang, ocr_version=ocr_version, use_angle_cls=True, show_log=False)
        cache = _cache_dirs(lang, ocr_version)

    # 2. Copy them into the project.
    info: dict[str, Any] = {
        "paddleocr_version": version,
        "ocr_version": ocr_version,
        "lang": lang,
        "copied_at": datetime.now().isoformat(timespec="seconds"),
        "models": {},
    }
    for role in ROLES:
        src, url = cache[role]
        dest = local[role]
        if not _has_model(src):
            print(f"[ERROR] {role.upper()} model not found in {src}")
            sys.exit(1)
        dest.mkdir(parents=True, exist_ok=True)
        # Remove model files left by other PaddleOCR versions (they share file names).
        for old in dest.iterdir():
            if old.is_file() and old.name != ".gitkeep":
                old.unlink()
        for name in MODEL_FILES:
            if (src / name).exists():
                shutil.copy2(src / name, dest / name)
        info["models"][role] = {"name": src.name, "source_url": url}
        print(f"  + {role.upper()}: {src.name}  ->  {dest}")

    (local["det"].parent / "model_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")

    print("\nInstalled models:")
    ok = show_status(local)
    print("\nDone. Check with:  python main.py --mode check-offline" if ok else "\nSome models are missing.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
