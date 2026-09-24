"""
setup_models.py
---------------
One-time bootstrap script: download PaddleOCR models to local directories
so the system can run fully offline thereafter.

IMPORTANT: Run this ONCE while you have internet access.
After completion, the system will NEVER need to go online again.

Usage:
    python setup_models.py

Compatible with PaddleOCR 2.x and 3.x.

What it downloads:
    • Detection model   → models/paddleocr/det/
    • Recognition model → models/paddleocr/rec/
    • Classifier model  → models/paddleocr/cls/

Settings are read from config/config.yaml.
"""

from __future__ import annotations

import inspect
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import yaml


# =========================================================================== #
# Helpers                                                                      #
# =========================================================================== #

def _load_config() -> dict:
    cfg_path = _ROOT / "config" / "config.yaml"
    with open(cfg_path, "r") as fh:
        return yaml.safe_load(fh) or {}


def _abs(rel: str) -> Path:
    p = Path(rel)
    return _ROOT / p if not p.is_absolute() else p


def _find_model_files(search_root: Path) -> list[Path]:
    """Recursively find PaddlePaddle inference model files."""
    model_exts = {".pdmodel", ".pdiparams", ".pdopt", ".nb"}
    found = []
    try:
        for ext in model_exts:
            found.extend(search_root.rglob(f"*{ext}"))
    except (PermissionError, OSError):
        pass
    return found


# =========================================================================== #
# Main                                                                         #
# =========================================================================== #

def main() -> None:
    print("=" * 60)
    print("  PaddleOCR Model Bootstrap")
    print("  (One-time online setup -- system runs offline afterwards)")
    print("=" * 60)

    config     = _load_config()
    paddle_cfg = config.get("paddleocr", {})
    lang       = paddle_cfg.get("lang", "en")

    det_dir = _abs(paddle_cfg.get("det_model_dir", "models/paddleocr/det"))
    rec_dir = _abs(paddle_cfg.get("rec_model_dir", "models/paddleocr/rec"))
    cls_dir = _abs(paddle_cfg.get("cls_model_dir", "models/paddleocr/cls"))

    print(f"\nLanguage        : {lang}")
    print(f"Detection dir   : {det_dir}")
    print(f"Recognition dir : {rec_dir}")
    print(f"Classifier dir  : {cls_dir}")

    for d in [det_dir, rec_dir, cls_dir]:
        d.mkdir(parents=True, exist_ok=True)

    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print(
            "\n[ERROR] paddleocr is not installed.\n"
            "        Install: pip install -r requirements.txt\n"
        )
        sys.exit(1)

    # Detect version
    import paddleocr as _poc
    version_str = getattr(_poc, "__version__", "2.0.0")
    major       = int(version_str.split(".")[0])
    print(f"\nPaddleOCR version: {version_str}")

    # Build minimal constructor kwargs (only what this version supports)
    valid_params = set(
        inspect.signature(PaddleOCR.__init__).parameters.keys()
    ) - {"self"}

    ocr_version = paddle_cfg.get("ocr_version", "PP-OCRv4")
    kwargs: dict[str, Any] = {"lang": lang}

    if major >= 3:
        if "ocr_version" in valid_params and ocr_version:
            kwargs["ocr_version"] = ocr_version
        if "use_doc_unwarping" in valid_params:
            kwargs["use_doc_unwarping"] = False
        if "use_doc_orientation_classify" in valid_params:
            kwargs["use_doc_orientation_classify"] = False
        if "use_textline_orientation" in valid_params:
            kwargs["use_textline_orientation"] = True
        # In 3.x, do NOT set model dirs here -- let it download to default location
    else:
        if "use_angle_cls"  in valid_params:  kwargs["use_angle_cls"] = True
        if "show_log"       in valid_params:  kwargs["show_log"] = True
        if "download_font"  in valid_params:  kwargs["download_font"] = True

    print(
        f"\nDownloading models for {ocr_version} (lang={lang})...\n"
        "Models will be cached and then copied to your local models/ directories.\n"
    )

    try:
        ocr = PaddleOCR(**kwargs)
        print("Download complete.")
    except Exception as exc:
        print(f"\n[ERROR] PaddleOCR initialisation failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Find downloaded model files and copy to our local dirs              #
    # ------------------------------------------------------------------ #
    search_roots = [
        Path.home() / ".paddleocr",
        Path.home() / ".paddlex",
        Path.home() / ".paddlepaddle",
        Path.home() / ".cache" / "paddleocr",
        Path.home() / ".cache" / "paddlex",
        Path.home() / "AppData" / "Local" / "paddleocr",
    ]

    # Add the paddleocr package directory itself (some versions store models there)
    try:
        import paddleocr as _poc_pkg
        pkg_dir = Path(_poc_pkg.__file__).parent
        search_roots.append(pkg_dir)
    except Exception:
        pass

    print(f"\nSearching for downloaded models in:")
    all_model_files: list[Path] = []
    for root in search_roots:
        if root.exists():
            files = _find_model_files(root)
            if files:
                print(f"  [FOUND {len(files)} file(s)] {root}")
                all_model_files.extend(files)
            else:
                print(f"  [empty]  {root}")
        else:
            print(f"  [missing] {root}")

    if not all_model_files:
        print(
            "\n[WARNING] Could not automatically locate downloaded model files.\n"
            "\nTo use the system offline, manually copy your model files:\n"
            f"  Detection  → {det_dir}\n"
            f"  Recognition → {rec_dir}\n"
            f"  Classifier  → {cls_dir}\n"
            "\nEach directory needs .pdmodel and .pdiparams files.\n"
            "You can also run `python main.py --mode ocr --input <file>` once while\n"
            "online -- PaddleOCR will download and cache models automatically.\n"
            "Then copy from the cache to models/paddleocr/det|rec|cls/.\n"
        )
        _print_cache_hint(search_roots, major)
        return

    # ── Copy all found model files ──────────────────────────────────────
    print(f"\nFound {len(all_model_files)} model file(s). Copying to local dirs...")
    _smart_copy(all_model_files, det_dir, rec_dir, cls_dir)

    # ── Final verification ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Verifying local model directories...")
    model_exts = {".pdmodel", ".pdiparams", ".pdopt", ".nb"}
    all_ok = True
    for label, d in [("DET", det_dir), ("REC", rec_dir), ("CLS", cls_dir)]:
        files = [f for f in d.iterdir() if f.suffix in model_exts]
        if files:
            print(f"  [OK] {label}: {len(files)} model file(s) in {d}")
        else:
            print(f"  [!!] {label}: No model files found in {d}")
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("\nSetup complete! Verify offline readiness:")
        print("    python main.py --mode check-offline")
    else:
        print(
            "\n[PARTIAL] Some model dirs are empty.\n"
            "See the hint above and copy files manually.\n"
            "Then run: python main.py --mode check-offline"
        )
    print()


def _smart_copy(
    model_files: list[Path],
    det_dir: Path,
    rec_dir: Path,
    cls_dir: Path,
) -> None:
    """
    Route each model file to the correct local directory based on its path keywords.
    """
    def _dest(f: Path) -> Path | None:
        path_str = str(f).lower()
        if any(kw in path_str for kw in ["det", "detect"]):
            return det_dir
        if any(kw in path_str for kw in ["rec", "recogn"]):
            return rec_dir
        if any(kw in path_str for kw in ["cls", "classif", "orient", "angle"]):
            return cls_dir
        return None

    placed = 0
    for f in model_files:
        dest_dir = _dest(f)
        if dest_dir is None:
            # Put files whose role can't be determined into det/ as a fallback
            dest_dir = det_dir
        dest_file = dest_dir / f.name
        if not dest_file.exists():
            try:
                shutil.copy2(str(f), str(dest_file))
                print(f"  + {f.name}  ->  {dest_dir.name}/")
                placed += 1
            except Exception as exc:
                print(f"  [WARN] Could not copy {f.name}: {exc}")
        else:
            print(f"  = {f.name}  (already in {dest_dir.name}/)")
    print(f"\nPlaced {placed} new file(s).")


def _print_cache_hint(search_roots: list[Path], major: int) -> None:
    """Print guidance on where to look for models manually."""
    print("\nTIP: You can trigger a download by running OCR on any image while online:")
    print("     python main.py --mode ocr --input input/sample.txt")
    print("     (This will fail gracefully but trigger PaddleOCR to download models.)")
    print(f"\nExpected PaddleOCR {major}.x cache location:")
    if major >= 3:
        print("  ~/.paddleocr/  or  ~/.paddlex/")
    else:
        print("  ~/.paddleocr/<version>/en/")


if __name__ == "__main__":
    main()
