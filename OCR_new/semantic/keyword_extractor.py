"""
semantic/keyword_extractor.py
------------------------------
Extract the most important keywords from a text using offline methods.

Strategy
--------
TF-IDF with scikit-learn's TfidfVectorizer over the sentences of the text
(scikit-learn is pinned in requirements.txt), with a simple word-frequency
count as a last resort.  No network access is required.
"""

from __future__ import annotations

import re
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


def extract_keywords(
    text: str,
    top_n: int = 10,
    language: str = "en",
) -> list[dict[str, Any]]:
    """
    Extract keywords from *text*.

    Parameters
    ----------
    text : str
        Raw OCR text.
    top_n : int
        Maximum number of keywords to return.
    language : str
        Language code (kept for compatibility; English stop words are used).

    Returns
    -------
    list[dict] each with::

        { "keyword": str, "score": float }

    Higher scores are more important; the most important keyword comes first.
    """
    text = text.strip()
    if not text:
        return []

    return _tfidf_extract(text, top_n=top_n)


def _tfidf_extract(text: str, top_n: int) -> list[dict[str, Any]]:
    """Simple TF-IDF over sentences as documents."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        import numpy as np

        sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 5]
        if not sentences:
            return _simple_frequency_extract(text, top_n)

        vectorizer = TfidfVectorizer(
            max_features=200,
            stop_words="english",
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(sentences)
        scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()
        feature_names = vectorizer.get_feature_names_out()

        top_indices = scores.argsort()[::-1][:top_n]
        return [
            {"keyword": feature_names[i], "score": round(float(scores[i]), 4)}
            for i in top_indices
        ]

    except ImportError:
        log.debug("scikit-learn not available — using simple frequency extraction.")
        return _simple_frequency_extract(text, top_n)


def _simple_frequency_extract(text: str, top_n: int) -> list[dict[str, Any]]:
    """Last-resort keyword extraction by word frequency."""
    stop_words = {
        "the", "a", "an", "is", "in", "on", "at", "to", "of", "and",
        "or", "for", "with", "by", "from", "as", "be", "was", "were",
        "are", "this", "that", "it", "its", "not", "but",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in stop_words:
            freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [
        {"keyword": word, "score": round(count / max(list(freq.values()) + [1]), 4)}
        for word, count in sorted_words[:top_n]
    ]
