"""Embedding model và vector DB (ChromaDB), tạo một lần rồi dùng lại."""
from __future__ import annotations

from .config import resolve

_model = None
_client = None


def get_model(cfg: dict):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(cfg["embedding_model"])
    return _model


def embed(cfg: dict, texts: list[str]) -> list[list[float]]:
    vecs = get_model(cfg).encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


def get_collection(cfg: dict, reset: bool = False):
    global _client
    import chromadb
    if _client is None:
        _client = chromadb.PersistentClient(path=str(resolve(cfg["vector_db_path"])))
    if reset:
        try:
            _client.delete_collection(cfg["collection"])
        except Exception:
            pass
    return _client.get_or_create_collection(
        cfg["collection"], metadata={"hnsw:space": "cosine"}
    )
