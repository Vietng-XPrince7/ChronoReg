"""Embedding bằng sentence-transformers (tải model một lần rồi dùng lại)."""
from __future__ import annotations

_model = None


def get_model(cfg: dict):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(cfg["embedding_model"])
    return _model


def embed(cfg: dict, texts: list[str]) -> list[list[float]]:
    vecs = get_model(cfg).encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()
