"""Vector DB (ChromaDB)."""
from __future__ import annotations

from .config import resolve

_client = None


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
