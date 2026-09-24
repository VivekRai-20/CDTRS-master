"""
utils/offline_checker.py
------------------------
Validates that all required local resources exist and that the system
is configured to run without internet access.

This module never triggers any model download — it only inspects the
file system and raises clear errors when something is missing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Tuple

from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Expected model sub-directories under models/paddleocr/
# ---------------------------------------------------------------------------
REQUIRED_MODEL_SUBDIRS = ["det", "rec", "cls"]


def _project_root() -> Path:
    """Return the absolute path to the project root (one level above utils/)."""
    return Path(__file__).resolve().parents[1]


def check_offline_mode(config: dict) -> None:
    """
    Validate that offline_mode is enabled in configuration.

    Raises
    ------
    SystemExit
        If offline_mode is explicitly set to False.
    """
    if not config.get("offline_mode", True):
        log.error(
            "offline_mode is set to 'false' in config.yaml. "
            "This system requires offline_mode: true for safe operation."
        )
        sys.exit(1)
    log.info("Offline mode: ENABLED")


def check_model_dirs(config: dict) -> Tuple[bool, list[str]]:
    """
    Verify that PaddleOCR model files are available locally.

    Checks two locations (in priority order):
      1. Our project's models/paddleocr/{det,rec,cls}/ directories.
      2. PaddleOCR 3.x system cache: ~/.paddlex/official_models/

    Parameters
    ----------
    config : dict
        The full application configuration dictionary.

    Returns
    -------
    (ok, missing_dirs)
        ok           – True if models are found in either location.
        missing_dirs – List of missing/empty directory paths (project local only).
    """
    root = _project_root()
    paddle_cfg = config.get("paddleocr", {})

    # Build expected paths from config (falls back to defaults)
    model_dirs = {
        "det": Path(paddle_cfg.get("det_model_dir", "models/paddleocr/det")),
        "rec": Path(paddle_cfg.get("rec_model_dir", "models/paddleocr/rec")),
        "cls": Path(paddle_cfg.get("cls_model_dir", "models/paddleocr/cls")),
    }

    model_exts = {".pdmodel", ".pdiparams", ".pdopt", ".nb"}
    missing: list[str] = []

    # ── Check 1: project-local model dirs ───────────────────────────────
    local_ok = True
    for label, rel_path in model_dirs.items():
        full_path = root / rel_path if not rel_path.is_absolute() else rel_path
        if not full_path.exists():
            missing.append(str(full_path))
            local_ok = False
            log.warning("Local model dir missing: %s  (%s)", label.upper(), full_path)
        else:
            model_files = [f for f in full_path.iterdir() if f.suffix.lower() in model_exts]
            if not model_files:
                missing.append(str(full_path))
                local_ok = False
                log.warning(
                    "Local model dir has no .pdmodel/.pdiparams files: %s  (%s)",
                    label.upper(), full_path,
                )
            else:
                log.info(
                    "Local model dir OK: %-4s  (%d file(s))  %s",
                    label.upper(), len(model_files), full_path,
                )

    if local_ok:
        return True, []

    # ── Check 2: PaddleOCR 3.x system cache (~/.paddlex/official_models) ─
    cache_roots = [
        Path.home() / ".paddlex" / "official_models",
        Path.home() / ".paddleocr",
        Path.home() / ".cache" / "paddleocr",
        Path.home() / ".cache" / "paddlex",
    ]

    cache_model_files: list[Path] = []
    for cache_root in cache_roots:
        if cache_root.exists():
            try:
                for ext in model_exts:
                    cache_model_files.extend(cache_root.rglob(f"*{ext}"))
            except (PermissionError, OSError):
                pass

    if cache_model_files:
        log.info(
            "System cache contains %d model file(s) under ~/.paddlex or ~/.paddleocr.",
            len(cache_model_files),
        )
        log.info(
            "Models are in the system cache but not yet copied to models/paddleocr/.\n"
            "Run `python setup_models.py` to copy them for explicit offline use.\n"
            "The system will still work using the cache location."
        )
        # System cache found — treat as OK for offline operation
        return True, []

    log.warning(
        "No model files found in local dirs OR system cache (~/.paddlex, ~/.paddleocr)."
    )
    return False, missing



def check_patterns_file(config: dict) -> bool:
    """
    Verify the patterns YAML file exists.

    Returns
    -------
    bool – True if the file exists.
    """
    root = _project_root()
    rel = config.get("paths", {}).get("patterns_file", "extraction/patterns.yaml")
    path = root / rel if not Path(rel).is_absolute() else Path(rel)

    if path.exists():
        log.info("Patterns file OK: %s", path)
        return True
    else:
        log.warning("Patterns file missing: %s", path)
        return False


def run_full_check(config: dict) -> None:
    """
    Run all offline checks.  Prints a comprehensive status report.
    Exits with code 1 if the system cannot operate offline.

    Parameters
    ----------
    config : dict
        The full application configuration dictionary.
    """
    print("\n" + "=" * 60)
    print("  OFFLINE READINESS CHECK")
    print("=" * 60)

    all_ok = True

    # 1 — offline_mode flag
    offline_on = config.get("offline_mode", True)
    status = "[OK] ENABLED" if offline_on else "[!!] DISABLED"
    print(f"\n[1] Offline mode flag        {status}")
    if not offline_on:
        all_ok = False

    # 2 — model directories
    models_ok, missing_dirs = check_model_dirs(config)
    status = "[OK] ALL PRESENT" if models_ok else f"[!!] MISSING ({len(missing_dirs)})"
    print(f"[2] PaddleOCR model dirs     {status}")
    if not models_ok:
        all_ok = False
        print("\n    Missing model directories:")
        for d in missing_dirs:
            print(f"      • {d}")
        print(
            "\n    ACTION REQUIRED:\n"
            "    Run the one-time model bootstrap (requires internet access):\n"
            "      python setup_models.py\n"
            "    Then retry.\n"
        )

    # 3 — patterns file
    patterns_ok = check_patterns_file(config)
    status = "[OK] FOUND" if patterns_ok else "[!!] NOT FOUND"
    print(f"[3] Patterns YAML file       {status}")
    if not patterns_ok:
        all_ok = False

    # Summary
    print("\n" + "=" * 60)
    if all_ok:
        print("  RESULT: System is READY for fully offline operation.")
    else:
        print("  RESULT: System is NOT ready. Fix issues above before running.")
    print("=" * 60 + "\n")

    if not all_ok:
        sys.exit(1)


def abort_if_models_missing(config: dict) -> None:
    """
    Called by the OCR engine before initialising PaddleOCR.
    Exits with a clear error instead of letting PaddleOCR auto-download.

    Parameters
    ----------
    config : dict
        The full application configuration dictionary.
    """
    ok, missing = check_model_dirs(config)
    if not ok:
        log.error(
            "\n\n"
            "  ERROR: PaddleOCR model files not found locally.\n"
            "  Offline mode is ENABLED — automatic downloads are blocked.\n\n"
            "  Please run the one-time setup script first (internet required):\n"
            "      python setup_models.py\n\n"
            "  After setup, models will be stored in:\n"
            "      models/paddleocr/det/\n"
            "      models/paddleocr/rec/\n"
            "      models/paddleocr/cls/\n\n"
            "  Missing paths:\n%s",
            "\n".join(f"    • {p}" for p in missing),
        )
        sys.exit(1)
