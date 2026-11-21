"""
Embedding Generation and Fast CPU Inference for WarpWeb
Uses fastembed with ONNX runtime for sub-10ms CPU text embedding.
Configurable model with sentence-transformers/all-MiniLM-L6-v2 as default.
"""
import os
import threading
from typing import List, Optional
import numpy as np

DEFAULT_MODEL_NAME = os.getenv("WARPWEB_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

class EmbeddingService:
    _instance = None
    _lock = threading.Lock()
    _model = None
    _loaded_model_name = None

    @classmethod
    def get_model(cls, model_name: str = DEFAULT_MODEL_NAME):
        with cls._lock:
            if cls._model is None or cls._loaded_model_name != model_name:
                from fastembed import TextEmbedding
                cls._model = TextEmbedding(model_name=model_name)
                cls._loaded_model_name = model_name
            return cls._model

    @classmethod
    def embed_documents(cls, texts: List[str], model_name: str = DEFAULT_MODEL_NAME) -> List[np.ndarray]:
        if not texts:
            return []
        model = cls.get_model(model_name)
        return [np.array(e, dtype=np.float32) for e in model.embed(texts)]

    @classmethod
    def embed_query(cls, query: str, model_name: str = DEFAULT_MODEL_NAME) -> np.ndarray:
        model = cls.get_model(model_name)
        embs = list(model.embed([query]))
        return np.array(embs[0], dtype=np.float32)

    @staticmethod
    def cosine_similarity(query_emb: np.ndarray, doc_embs: np.ndarray) -> np.ndarray:
        """
        Computes cosine similarities between a 1D query vector and a 2D matrix of doc vectors.
        doc_embs: shape (N, D)
        query_emb: shape (D,)
        Returns: shape (N,) cosine scores between -1.0 and 1.0.
        """
        if doc_embs.size == 0 or query_emb.size == 0:
            return np.array([], dtype=np.float32)

        q_norm = np.linalg.norm(query_emb)
        if q_norm == 0:
            return np.zeros(doc_embs.shape[0], dtype=np.float32)

        doc_norms = np.linalg.norm(doc_embs, axis=1)
        doc_norms = np.where(doc_norms == 0, 1e-9, doc_norms)

        dots = np.dot(doc_embs, query_emb)
        return dots / (doc_norms * q_norm)
