"""
semantic/embedding_engine.py
-----------------------------
Local sentence embedding engine using a locally stored Sentence-Transformer
compatible model.

Model storage
-------------
Place the model under::

    models/embeddings/model/

The directory must contain all model files (config.json, tokenizer files,
pytorch_model.bin or model.safetensors, etc.).

The engine loads with ``local_files_only=True`` — no internet access is
used during inference.

Configuration
-------------
Relevant config.yaml key::

    semantic:
      embedding_model: "models/embeddings/model"
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EmbeddingEngine:
    """
    Generates dense text embeddings using a locally stored model.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._model = None
        self._model_path: Path | None = None
        self._initialized = False

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """
        Load the local embedding model.

        Raises
        ------
        FileNotFoundError
            If the model directory does not exist.
        RuntimeError
            If the ``sentence-transformers`` package is not installed.
        """
        sem_cfg = self._config.get("semantic", {})
        model_path_str = sem_cfg.get("embedding_model", "models/embeddings/model")
        model_path = Path(model_path_str)
        if model_path.is_absolute():
            self._model_path = model_path
        else:
            self._model_path = (_PROJECT_ROOT / model_path).resolve()

        self._check_model_exists()
        self._load_model()
        self._initialized = True
        log.info("EmbeddingEngine loaded from '%s'.", self._model_path)

    def encode(
        self,
        texts: Union[str, list[str]],
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Generate embeddings for *texts*.

        Parameters
        ----------
        texts : str or list[str]
        normalize : bool
            If True, L2-normalise the output vectors (default True).
            Normalised embeddings allow cosine similarity via dot product.

        Returns
        -------
        np.ndarray of shape (N, embedding_dim) or (embedding_dim,) for
        a single string input.
        """
        if not self._initialized:
            self.initialize()

        if isinstance(texts, str):
            texts = [texts]
            single = True
        else:
            single = False

        embeddings = self._model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        return embeddings[0] if single else embeddings

    @property
    def embedding_dim(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        if not self._initialized:
            self.initialize()
        return int(self._model.get_sentence_embedding_dimension())

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _check_model_exists(self) -> None:
        if self._model_path is None or not self._model_path.exists():
            raise FileNotFoundError(
                "\n"
                "========================================\n"
                "ERROR: Required model is not available locally.\n\n"
                "Model:\n"
                "  embedding_model\n\n"
                "Expected location:\n"
                f"  {self._model_path}\n\n"
                "Offline mode is enabled.\n"
                "Automatic downloads are disabled.\n"
                "========================================\n"
            )

    def _load_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                str(self._model_path),
                local_files_only=True,
            )
        except ImportError:
            raise RuntimeError(
                "The 'sentence-transformers' package is required.\n"
                "Install with:  pip install sentence-transformers"
            )
