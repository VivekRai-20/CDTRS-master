"""semantic package"""
from semantic.embedding_engine import EmbeddingEngine
from semantic.semantic_similarity import cosine_similarity, rank_by_similarity
from semantic.document_classifier import SemanticDocumentClassifier
from semantic.keyword_extractor import extract_keywords
from semantic.semantic_pipeline import SemanticPipeline

__all__ = [
    "EmbeddingEngine",
    "cosine_similarity",
    "rank_by_similarity",
    "SemanticDocumentClassifier",
    "extract_keywords",
    "SemanticPipeline",
]
