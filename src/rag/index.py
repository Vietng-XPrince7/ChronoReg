"""Nạp chunk vào vector DB.

Chạy:  python -m src.rag.index
(cần có file chunk: python -m src.versioning.cli export-chunks --include-unreviewed --max-chars 1500)
"""
from __future__ import annotations

from . import embedder, store
from .chunker import load_chunks
from .config import load_config, resolve


def build_index(cfg: dict | None = None, reset: bool = True, batch: int = 32) -> int:
    cfg = cfg or load_config()
    path = resolve(cfg["chunks_file"])
    if not path.exists():
        raise SystemExit(f"Chưa có {path}. Chạy: python -m src.versioning.cli export-chunks "
                         "--include-unreviewed --max-chars 1500")
    chunks = load_chunks(path, resolve(cfg["reviewed_documents_file"]))
    if not chunks:
        raise SystemExit(f"{path} không có chunk nào.")
    col = store.get_collection(cfg, reset=reset)
    for i in range(0, len(chunks), batch):
        b = chunks[i:i + batch]
        col.upsert(
            ids=[c.id for c in b],
            documents=[c.document for c in b],
            embeddings=embedder.embed(cfg, [c.text for c in b]),
            metadatas=[c.metadata for c in b],
        )
    return len(chunks)


if __name__ == "__main__":
    print(f"Đã nạp {build_index()} chunk vào vector DB.")
