"""
Embedding Generation and Fast CPU Inference for WarpWeb
Uses fastembed with ONNX runtime for sub-10ms CPU text embedding.
Configurable model with sentence-transformers/all-MiniLM-L6-v2 as default.
Provides graceful degradation to BM25-only when model fails or is unavailable.
"""
import os
import threading
import logging
from typing import List, Optional
import numpy as np

logger = logging.getLogger("warpweb.embeddings")

DEFAULT_MODEL_NAME = os.getenv("WARPWEB_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

class EmbeddingService:
    _instance = None
    _lock = threading.Lock()
    _model = None
    _loaded_model_name = None
    _is_degraded = False
    _degradation_reason: Optional[str] = None

    @classmethod
    def get_status(cls) -> str:
        """Returns health status of the embedding service: 'healthy' or 'degraded_bm25_only'."""
        return "degraded_bm25_only" if cls._is_degraded else "healthy"

    @classmethod
    def is_degraded(cls) -> bool:
        return cls._is_degraded

    @classmethod
    def reset_status(cls):
        """Resets degradation status (primarily for testing and re-initialization)."""
        with cls._lock:
            cls._model = None
            cls._loaded_model_name = None
            cls._is_degraded = False
            cls._degradation_reason = None

    @classmethod
    def get_model(cls, model_name: str = DEFAULT_MODEL_NAME):
        with cls._lock:
            if cls._is_degraded:
                return None
            if cls._model is None or cls._loaded_model_name != model_name:
                try:
                    from fastembed import TextEmbedding
                    cls._model = TextEmbedding(model_name=model_name)
                    cls._loaded_model_name = model_name
                    cls._is_degraded = False
                    cls._degradation_reason = None
                except Exception as e:
                    cls._is_degraded = True
                    cls._degradation_reason = str(e)
                    logger.warning(
                        "Embedding model '%s' failed to load (%s). Gracefully degrading to BM25-only.",
                        model_name, e
                    )
                    return None
            return cls._model

    @classmethod
    def embed_documents(cls, texts: List[str], model_name: str = DEFAULT_MODEL_NAME) -> List[Optional[np.ndarray]]:
        if not texts:
            return []
        try:
            model = cls.get_model(model_name)
            if model is None:
                return [None] * len(texts)
            return [np.array(e, dtype=np.float32) for e in model.embed(texts)]
        except Exception as e:
            cls._is_degraded = True
            cls._degradation_reason = str(e)
            logger.warning("Batch embedding generation failed (%s). Gracefully degrading to BM25-only.", e)
            return [None] * len(texts)

    @classmethod
    def embed_query(cls, query: str, model_name: str = DEFAULT_MODEL_NAME) -> Optional[np.ndarray]:
        try:
            model = cls.get_model(model_name)
            if model is None:
                return None
            embs = list(model.embed([query]))
            return np.array(embs[0], dtype=np.float32)
        except Exception as e:
            cls._is_degraded = True
            cls._degradation_reason = str(e)
            logger.warning("Query embedding generation failed (%s). Gracefully degrading to BM25-only.", e)
            return None

    @staticmethod
    def cosine_similarity(query_emb: np.ndarray, doc_embs: np.ndarray) -> np.ndarray:
        """
        Computes cosine similarities between a 1D query vector and a 2D matrix of doc vectors.
        doc_embs: shape (N, D)
        query_emb: shape (D,)
        Returns: shape (N,) cosine scores between -1.0 and 1.0.
        """
        if query_emb is None or doc_embs is None or doc_embs.size == 0 or query_emb.size == 0:
            return np.array([], dtype=np.float32)

        q_norm = np.linalg.norm(query_emb)
        if q_norm == 0:
            return np.zeros(doc_embs.shape[0], dtype=np.float32)

        doc_norms = np.linalg.norm(doc_embs, axis=1)
        doc_norms = np.where(doc_norms == 0, 1e-9, doc_norms)

        dots = np.dot(doc_embs, query_emb)
        return dots / (doc_norms * q_norm)
