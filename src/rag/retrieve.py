"""Truy xuất các Điều liên quan, đã lọc theo phiên bản NGAY TRONG truy vấn."""
from __future__ import annotations

from . import store
from .versioning import VersionPlan


def retrieve(question: str, plan: VersionPlan, cfg: dict) -> list[dict]:
    col = store.get_collection(cfg)
    kwargs = {
        "query_embeddings": store.embed(cfg, [question]),
        "n_results": cfg.get("top_k", 5),
    }
    where = plan.where()
    if where:
        kwargs["where"] = where
    res = col.query(**kwargs)
    return [
        {"document": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
