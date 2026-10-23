"""Nạp các Điều đã chunk vào vector DB.

Chạy:  python -m src.rag.index
"""
from __future__ import annotations

from . import store
from .chunking import load_processed
from .config import load_config, resolve


def build_index(cfg: dict | None = None, reset: bool = True, batch: int = 32) -> int:
    cfg = cfg or load_config()
    chunks = load_processed(resolve(cfg["data_dir"]))
    if not chunks:
        raise SystemExit(f"Không có chunk nào trong {cfg['data_dir']} (ingestion đã chạy chưa?)")
    col = store.get_collection(cfg, reset=reset)
    for i in range(0, len(chunks), batch):
        b = chunks[i:i + batch]
        col.upsert(
            ids=[c.id for c in b],
            documents=[c.document for c in b],
            embeddings=store.embed(cfg, [c.text for c in b]),
            metadatas=[c.metadata for c in b],
        )
    return len(chunks)


if __name__ == "__main__":
    print(f"Đã nạp {build_index()} Điều vào vector DB.")
