"""
testing/test_semantic.py
-------------------------
Unit tests for the semantic module.
(Tests that don't require the embedding model to be present.)
"""

from __future__ import annotations

import numpy as np
import unittest

from semantic.semantic_similarity import cosine_similarity, rank_by_similarity, batch_similarity_matrix
from semantic.keyword_extractor import extract_keywords


class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        assert abs(cosine_similarity(a, a) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_zero_vector_returns_zero(self):
        a = np.zeros(3)
        b = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(a, b) == 0.0

    def test_similar_vectors_high_score(self):
        a = np.array([1.0, 1.0, 1.0])
        b = np.array([1.0, 1.0, 0.9])
        sim = cosine_similarity(a, b)
        assert sim > 0.98


class TestRankBySimilarity(unittest.TestCase):
    def test_ranking_order(self):
        query = np.array([1.0, 0.0])
        candidates = [
            {"label": "A", "embedding": np.array([1.0, 0.0])},
            {"label": "B", "embedding": np.array([0.0, 1.0])},
            {"label": "C", "embedding": np.array([0.7, 0.7])},
        ]
        result = rank_by_similarity(query, candidates)
        assert result[0]["label"] == "A"
        assert result[-1]["label"] == "B"

    def test_top_k(self):
        query = np.array([1.0, 0.0])
        candidates = [
            {"label": str(i), "embedding": np.random.default_rng(i).random(2)}
            for i in range(10)
        ]
        result = rank_by_similarity(query, candidates, top_k=3)
        assert len(result) == 3

    def test_empty_candidates(self):
        query = np.array([1.0, 0.0])
        result = rank_by_similarity(query, [])
        assert result == []


class TestBatchSimilarityMatrix(unittest.TestCase):
    def test_shape(self):
        A = np.random.rand(3, 4)
        B = np.random.rand(5, 4)
        M = batch_similarity_matrix(A, B)
        assert M.shape == (3, 5)

    def test_diagonal_near_one(self):
        A = np.eye(4)
        M = batch_similarity_matrix(A, A)
        assert all(abs(M[i, i] - 1.0) < 1e-6 for i in range(4))


class TestKeywordExtractor(unittest.TestCase):
    def test_extract_keywords_returns_list(self):
        text = "The quick brown fox jumps over the lazy dog repeatedly."
        result = extract_keywords(text, top_n=5)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_extract_keywords_empty_text(self):
        result = extract_keywords("", top_n=5)
        assert result == []

    def test_each_keyword_has_required_keys(self):
        text = "Machine learning models are trained on large datasets for classification tasks."
        result = extract_keywords(text, top_n=3)
        for kw in result:
            assert "keyword" in kw
            assert "score" in kw
