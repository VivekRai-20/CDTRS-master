"""
semantic/semantic_similarity.py
--------------------------------
Cosine similarity utilities for embedding vectors.

Used by:
  - document_classifier.py  (compare doc embedding to category embeddings)
  - semantic_pipeline.py    (compare two documents)
  - extraction/semantic_extractor.py
"""

from __future__ import annotations

from typing import Any

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two 1-D embedding vectors.

    Parameters
    ----------
    a, b : np.ndarray
        1-D float arrays of the same length.

    Returns
    -------
    float in [-1.0, 1.0].  Returns 0.0 if either vector is zero.
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def rank_by_similarity(
    query_embedding: np.ndarray,
    candidates: list[dict[str, Any]],
    embedding_key: str = "embedding",
    label_key: str = "label",
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """
    Rank *candidates* by cosine similarity to *query_embedding*.

    Parameters
    ----------
    query_embedding : np.ndarray
        1-D embedding of the query.
    candidates : list[dict]
        Each dict must have keys ``embedding_key`` (np.ndarray) and
        ``label_key`` (str).
    embedding_key : str
        Key in candidate dicts that holds the embedding.
    label_key : str
        Key in candidate dicts that holds the label string.
    top_k : int, optional
        If given, return only the top-k results.

    Returns
    -------
    list[dict] sorted descending by similarity, each with::

        { "label": str, "similarity": float }
    """
    results = []
    for cand in candidates:
        emb = cand.get(embedding_key)
        label = cand.get(label_key, "UNKNOWN")
        if emb is None:
            continue
        sim = cosine_similarity(query_embedding, np.asarray(emb))
        results.append({"label": label, "similarity": round(sim, 4)})

    results.sort(key=lambda x: x["similarity"], reverse=True)
    if top_k is not None:
        results = results[:top_k]
    return results


def batch_similarity_matrix(
    embeddings_a: np.ndarray,
    embeddings_b: np.ndarray,
) -> np.ndarray:
    """
    Compute pairwise cosine similarities between two sets of embeddings.

    Parameters
    ----------
    embeddings_a : np.ndarray, shape (N, D)
    embeddings_b : np.ndarray, shape (M, D)

    Returns
    -------
    np.ndarray, shape (N, M)
        sim[i, j] = cosine_similarity(a[i], b[j])
    """
    # Normalise rows
    norms_a = np.linalg.norm(embeddings_a, axis=1, keepdims=True)
    norms_b = np.linalg.norm(embeddings_b, axis=1, keepdims=True)
    norms_a = np.where(norms_a == 0, 1.0, norms_a)
    norms_b = np.where(norms_b == 0, 1.0, norms_b)
    a_norm = embeddings_a / norms_a
    b_norm = embeddings_b / norms_b
    return a_norm @ b_norm.T
