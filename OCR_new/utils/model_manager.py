"""
utils/model_manager.py
-----------------------
Manage locally stored models: discovery, version tracking, and clear
error reporting when a required model is missing.

Design goals
------------
* The runtime NEVER silently downloads a missing model.
* If a model is missing, a clear, actionable error is raised.
* Models can be versioned (v1/, v2/, v3/…) and the active version is
  configurable.
* Metadata (training date, dataset, metrics) is stored alongside each
  model version as ``model_meta.json``.

Model directory structure
--------------------------
::

    models/
    ├── paddleocr/
    │   ├── det/
    │   ├── rec/
    │   └── cls/
    ├── handwriting/
    │   ├── v1/
    │   ├── v2/
    │   └── current -> v2/  (symlink or active.txt)
    ├── embeddings/
    │   └── model/
    ├── ner/
    ├── classifiers/
    │   ├── document/
    │   └── text_type/
    └── layout/

Usage
-----
::

    from utils.model_manager import ModelManager

    mm = ModelManager(config)
    mm.verify_required()                # raises if any required model is missing
    model_path = mm.get_path("handwriting")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)

# Required model paths relative to the models/ directory
_REQUIRED_MODELS: dict[str, str] = {
    "paddleocr":   "paddleocr",
    "embeddings":  "embeddings",
    "ner":         "ner",
    "classifiers": "classifiers",
    "layout":      "layout",
}

# Optional models (missing = feature degraded, not fatal)
_OPTIONAL_MODELS: dict[str, str] = {
    "handwriting": "handwriting",
}


class ModelManager:
    """
    Manages local model directories and metadata.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        root = Path(__file__).resolve().parents[1]
        paths_cfg = self._config.get("paths", {})
        self._models_dir = root / paths_cfg.get("models_dir", "models")

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def verify_required(self) -> None:
        """
        Check all required models are present.

        Raises
        ------
        FileNotFoundError
            With a clear message if any required model directory is missing
            or empty.
        """
        for model_name, rel_path in _REQUIRED_MODELS.items():
            model_dir = self._models_dir / rel_path
            if not model_dir.exists():
                self._raise_missing(model_name, model_dir)
            # Existence of any file (not just the directory) is required
            # for some models (e.g. paddleocr has sub-dirs)

        log.info("All required models are present.")

    def check_all(self) -> dict[str, bool]:
        """
        Check availability of all known models (required + optional).

        Returns
        -------
        dict mapping model_name → True/False
        """
        results: dict[str, bool] = {}
        all_models = {**_REQUIRED_MODELS, **_OPTIONAL_MODELS}
        for model_name, rel_path in all_models.items():
            model_dir = self._models_dir / rel_path
            results[model_name] = model_dir.exists()
        return results

    def get_path(self, model_name: str, version: str | None = None) -> Path:
        """
        Return the path to a model directory.

        Parameters
        ----------
        model_name : str
            e.g. "handwriting", "embeddings"
        version : str, optional
            e.g. "v2".  If None, uses the active version (from
            ``active.txt`` or the latest ``vN`` subdirectory).

        Returns
        -------
        Path

        Raises
        ------
        FileNotFoundError
            If the model directory does not exist.
        """
        all_models = {**_REQUIRED_MODELS, **_OPTIONAL_MODELS}
        rel_path = all_models.get(model_name)
        if rel_path is None:
            raise ValueError(f"Unknown model name: '{model_name}'")

        model_dir = self._models_dir / rel_path

        if version:
            versioned = model_dir / version
            if not versioned.exists():
                raise FileNotFoundError(
                    f"Model version '{version}' not found: {versioned}"
                )
            return versioned

        # Auto-detect active version
        active = self._resolve_active_version(model_dir)
        if active is not None:
            return active

        if not model_dir.exists():
            self._raise_missing(model_name, model_dir)
        return model_dir

    def get_metadata(self, model_path: Path) -> dict[str, Any]:
        """
        Load ``model_meta.json`` from *model_path* if it exists.

        Returns
        -------
        dict  — empty dict if no metadata file exists.
        """
        meta_file = model_path / "model_meta.json"
        if not meta_file.exists():
            return {}
        try:
            with open(meta_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            log.warning("Could not read model metadata from '%s': %s", meta_file, exc)
            return {}

    def save_metadata(self, model_path: Path, metadata: dict[str, Any]) -> None:
        """
        Write metadata to ``model_meta.json`` inside *model_path*.
        """
        model_path.mkdir(parents=True, exist_ok=True)
        meta_file = model_path / "model_meta.json"
        with open(meta_file, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2, ensure_ascii=False)
        log.debug("Saved model metadata to '%s'.", meta_file)

    def list_versions(self, model_name: str) -> list[str]:
        """
        List available version directories for *model_name*.

        Returns
        -------
        list[str]  – version names (e.g. ["v1", "v2"]), sorted.
        """
        all_models = {**_REQUIRED_MODELS, **_OPTIONAL_MODELS}
        rel_path = all_models.get(model_name)
        if rel_path is None:
            return []
        model_dir = self._models_dir / rel_path
        if not model_dir.exists():
            return []
        return sorted(
            d.name for d in model_dir.iterdir()
            if d.is_dir() and d.name.startswith("v")
        )

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _resolve_active_version(self, model_dir: Path) -> Path | None:
        """
        Try to find the active version directory.

        Looks for:
        1.  ``active.txt`` containing a version name.
        2.  The highest-numbered ``vN`` subdirectory.
        """
        if not model_dir.exists():
            return None

        active_file = model_dir / "active.txt"
        if active_file.exists():
            version_name = active_file.read_text(encoding="utf-8").strip()
            versioned = model_dir / version_name
            if versioned.exists():
                return versioned

        # Find highest vN directory
        version_dirs = sorted(
            (d for d in model_dir.iterdir() if d.is_dir() and d.name.startswith("v")),
            key=lambda d: d.name,
        )
        if version_dirs:
            return version_dirs[-1]

        return None

    @staticmethod
    def _raise_missing(model_name: str, model_dir: Path) -> None:
        raise FileNotFoundError(
            "\n"
            "========================================\n"
            "ERROR: Required model is not available locally.\n\n"
            f"Model:\n"
            f"  {model_name}\n\n"
            f"Expected location:\n"
            f"  {model_dir}\n\n"
            "Offline mode is enabled.\n"
            "Automatic downloads are disabled.\n"
            "========================================\n"
            f"Please place the model files in:\n"
            f"  {model_dir}\n"
            "and re-run the application.\n"
        )
