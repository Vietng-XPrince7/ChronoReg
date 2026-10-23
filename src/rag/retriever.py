"""Truy xuất chunk, lọc phiên bản (năm học) NGAY TRONG truy vấn."""
from __future__ import annotations

from collections import Counter

from . import embedder, store
from .versioning import VersionPlan


def _query(cfg: dict, question: str, where: dict | None, n: int) -> list[dict]:
    kwargs = {"query_embeddings": embedder.embed(cfg, [question]), "n_results": n}
    if where:
        kwargs["where"] = where
    res = store.get_collection(cfg).query(**kwargs)
    return [
        {"document": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def latest_by_topic(cfg: dict) -> tuple[dict[str, int], int]:
    """Năm bắt đầu mới nhất theo chủ đề (chỉ tính chunk đã biết năm học) và mới nhất toàn cục."""
    metas = store.get_collection(cfg).get(include=["metadatas"])["metadatas"]
    out: dict[str, int] = {}
    for m in metas:
        if m["start_year"]:
            t = m["topic_hint"]
            out[t] = max(out.get(t, 0), m["start_year"])
    return out, max(out.values(), default=0)


def retrieve(question: str, plan: VersionPlan, cfg: dict) -> tuple[list[dict], VersionPlan]:
    """-> (hits, plan). Ở chế độ "latest", plan được cập nhật năm học đã chọn."""
    k = cfg.get("top_k", 5)
    if plan.mode != "latest":
        return _query(cfg, question, plan.where(), k), plan

    # "latest": đoán chủ đề từ các kết quả gần nhất (không lọc), rồi lấy năm học mới nhất của chủ đề đó
    probe = _query(cfg, question, None, max(k * 3, 10))
    if not probe:
        return [], plan
    by_topic, overall = latest_by_topic(cfg)
    topic = Counter(h["metadata"]["topic_hint"] for h in probe[:3]).most_common(1)[0][0]
    year = by_topic.get(topic) or overall
    if not year:   # chưa chunk nào biết năm học
        return probe[:k], VersionPlan("latest", None, plan.reason + " (không chunk nào biết năm học)")
    where = {"$and": [{"topic_hint": topic}, {"start_year": year}]} if topic in by_topic \
        else {"start_year": year}
    new_plan = VersionPlan("latest", year, f"{plan.reason}: chủ đề '{topic or '?'}' -> {year}-{year + 1}")
    return _query(cfg, question, where, k), new_plan
