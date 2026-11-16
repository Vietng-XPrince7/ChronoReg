"""Retrieve chunks from ChromaDB with both version (academic year) and topic filtering."""
from __future__ import annotations

from . import embedder, store
from .eval_adapter import detect_topic
from .versioning import VersionPlan, extract_article


def _and(a: dict | None, b: dict | None) -> dict | None:
    if a and b:
        return {"$and": [a, b]}
    return a or b


def _query(cfg: dict, question: str, where: dict | None, k: int) -> list[dict]:
    col = store.get_collection(cfg)
    total = col.count() if hasattr(col, "count") else len(getattr(col, "rows", []))
    if total == 0:
        return []
    q_emb = embedder.embed(cfg, [question])[0]
    res = col.query(
        query_embeddings=[q_emb],
        n_results=min(k, total),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    docs = (res.get("documents") or [[]])[0]
    ids = (res.get("ids") or [[]])[0]
    if not ids and docs:
        ids = [f"id_{idx}" for idx in range(len(docs))]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    return [
        {"id": i, "document": d, "metadata": m, "score": 1.0 - float(dist)}
        for i, d, m, dist in zip(ids, docs, metas, dists)
    ]


def _wheres(plan: VersionPlan, topic: str = "") -> list[dict | None]:
    """Build ChromaDB metadata filters combining temporal plan and inferred topic."""
    topic_filter = {"topic_hint": topic} if topic else None
    if plan.mode == "year":
        base_wheres = [plan.where_for(y) for y in plan.all_years()] or [None]
        return [_and(w, topic_filter) for w in base_wheres]
    if plan.mode == "latest":
        return [_and({"latest_in_topic": 1}, topic_filter)]
    return [topic_filter]


def _interleave(lists: list[list[dict]], n: int) -> list[dict]:
    out = [
        lst[i]
        for i in range(max((len(x) for x in lists), default=0))
        for lst in lists
        if i < len(lst)
    ]
    return out[:n]


def retrieve(question: str, plan: VersionPlan, cfg: dict) -> tuple[list[dict], VersionPlan]:
    """Retrieve top-k chunks with topic and academic-year constraints."""
    k = cfg.get("top_k", 5)
    inferred_topic = detect_topic(question)

    wheres = _wheres(plan, topic=inferred_topic)
    per = k if len(wheres) == 1 else max(2, -(-k // len(wheres)))
    hits = _interleave([_query(cfg, question, w, per) for w in wheres], k)

    # Fallback 1: If topic_hint in ChromaDB was stored as 'other', retry without topic filter
    if not hits and inferred_topic:
        wheres_no_topic = _wheres(plan, topic="")
        hits = _interleave([_query(cfg, question, w, per) for w in wheres_no_topic], k)

    # Fallback 2: If latest_in_topic flag is missing in an older index, query unfiltered
    if plan.mode == "latest" and not hits:
        hits = _query(cfg, question, None, k)
        plan = VersionPlan("latest", None, plan.reason + " (fallback unfiltered)")

    art = extract_article(question)
    if art:
        art_hits = _interleave(
            [_query(cfg, question, _and(w, {"dieu_so": art}), 2) for w in wheres], 2
        )
        seen = {h["document"] for h in art_hits}
        hits = (art_hits + [h for h in hits if h["document"] not in seen])[:k]

    if plan.mode == "latest" and hits:
        years = sorted(
            {h["metadata"]["start_year"] for h in hits if h["metadata"].get("start_year")},
            reverse=True,
        )
        if years:
            plan = VersionPlan(
                "latest",
                years[0],
                "không nêu năm -> văn bản mới nhất của từng chủ đề",
                tuple(years),
            )
    return hits, plan