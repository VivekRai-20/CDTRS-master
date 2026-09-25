"""
utils/logger.py
---------------
Centralised logging factory for the offline OCR system.

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Processing started")
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional


def _load_config() -> dict:
    """Load logging sub-section from config.yaml without circular imports."""
    try:
        import yaml
        config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        return cfg.get("logging", {})
    except Exception:
        return {}


def setup_root_logger(config: Optional[dict] = None) -> None:
    """
    Configure the root logger once at application startup.
    Subsequent calls to get_logger() inherit this configuration.

    Parameters
    ----------
    config : dict, optional
        A dict matching the 'logging' section of config.yaml.
        If None, the config file is read automatically.
    """
    if config is None:
        config = _load_config()

    level_str = config.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        # Already configured — skip to avoid duplicate handlers
        return

    root.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)-35s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Console handler ------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    # --- File handler (optional) ----------------------------------------
    if config.get("log_to_file", True):
        log_dir = Path(config.get("log_dir", "output"))
        if not log_dir.is_absolute():  # relative to OCR_new, not the current folder
            log_dir = Path(__file__).resolve().parents[1] / log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / config.get("log_file", "ocr_system.log")

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=int(config.get("max_bytes", 5 * 1024 * 1024)),
            backupCount=int(config.get("backup_count", 3)),
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Suppress overly verbose third-party loggers
    for noisy in ("ppocr", "paddle", "PIL", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.  Call setup_root_logger() at application startup
    before calling this for the first time.

    Parameters
    ----------
    name : str
        Typically pass ``__name__`` from the calling module.
    """
    return logging.getLogger(name)
