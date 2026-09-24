"""
semantic/keyword_extractor.py
------------------------------
Extract the most important keywords from a text using offline methods.

Two strategies
--------------
1.  **YAKE** (Yet Another Keyword Extractor) — unsupervised, language-
    agnostic, offline.  Preferred when the ``yake`` package is installed.
2.  **TF-IDF fallback** — uses scikit-learn's TfidfVectorizer on the
    input text split into sentences.

No network access is required for either strategy.
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
        Language code (used by YAKE).

    Returns
    -------
    list[dict] each with::

        { "keyword": str, "score": float }

    Score semantics differ by strategy (lower is better for YAKE;
    higher is better for TF-IDF), but results are always sorted so
    that the most important keyword appears first.
    """
    text = text.strip()
    if not text:
        return []

    # --- 1. YAKE ---
    try:
        return _yake_extract(text, top_n=top_n, language=language)
    except ImportError:
        log.debug("YAKE not available — falling back to TF-IDF keyword extraction.")

    # --- 2. TF-IDF ---
    return _tfidf_extract(text, top_n=top_n)


# ──────────────────────────────────────────────────────────────────────────────
# Strategy implementations
# ──────────────────────────────────────────────────────────────────────────────

def _yake_extract(
    text: str, top_n: int, language: str
) -> list[dict[str, Any]]:
    import yake  # type: ignore

    extractor = yake.KeywordExtractor(
        lan=language,
        n=3,           # max n-gram size
        dedupLim=0.9,
        top=top_n,
    )
    keywords = extractor.extract_keywords(text)
    # YAKE: lower score = more important → sort ascending
    keywords.sort(key=lambda kw: kw[1])
    return [{"keyword": kw, "score": round(score, 4)} for kw, score in keywords]


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
