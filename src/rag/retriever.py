"""Truy xuất chunk, lọc phiên bản (năm học) NGAY TRONG truy vấn."""
from __future__ import annotations

from . import embedder, store
from .versioning import VersionPlan, extract_article


def _query(cfg: dict, question: str, where: dict | None, n: int) -> list[dict]:
    kwargs = {"query_embeddings": embedder.embed(cfg, [question]), "n_results": n}
    if where:
        kwargs["where"] = where
    res = store.get_collection(cfg).query(**kwargs)
    return [
        {"document": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def _and(where: dict | None, extra: dict) -> dict:
    if not where:
        return extra
    if "$and" in where:
        return {"$and": [*where["$and"], extra]}
    return {"$and": [where, extra]}


def _wheres(plan: VersionPlan) -> list[dict | None]:
    """Các điều kiện lọc theo chế độ: mỗi năm học một điều kiện; "latest" = năm học mới nhất
    của từng chủ đề; "all" = không lọc."""
    if plan.mode == "year":
        return [plan.where_for(y) for y in plan.all_years()] or [None]
    if plan.mode == "latest":
        return [{"latest_in_topic": 1}]
    return [None]


def _interleave(lists: list[list[dict]], n: int) -> list[dict]:
    out = [lst[i] for i in range(max((len(x) for x in lists), default=0)) for lst in lists if i < len(lst)]
    return out[:n]


def _group_balanced(lists: list[list[dict]], n: int) -> list[dict]:
    """Lấy cân bằng từ mỗi năm học nhưng giữ các đoạn cùng năm đứng liền nhau để tránh trộn phiên bản."""
    if not lists:
        return []
    if len(lists) == 1:
        return lists[0][:n]
    # Phân bổ hạn mức cân bằng từng năm (vòng tròn chỉ để đếm quota, sau đó xuất theo từng nhóm năm)
    counts = [0] * len(lists)
    total = 0
    progress = True
    while total < n and progress:
        progress = False
        for idx, lst in enumerate(lists):
            if counts[idx] < len(lst) and total < n:
                counts[idx] += 1
                total += 1
                progress = True
    out: list[dict] = []
    seen: set[str] = set()
    for idx, lst in enumerate(lists):
        for h in lst[:counts[idx]]:
            doc_key = f"{h.get('metadata', {}).get('doc_id', '')}::{h.get('document', '')}"
            if doc_key not in seen:
                seen.add(doc_key)
                out.append(h)
    return out[:n]


def retrieve(question: str, plan: VersionPlan, cfg: dict) -> tuple[list[dict], VersionPlan]:
    """-> (hits, plan). Ở chế độ "latest", plan được cập nhật các năm học đã dùng."""
    k = cfg.get("top_k", 5)
    wheres = _wheres(plan)
    per = k if len(wheres) == 1 else max(2, -(-k // len(wheres)))   # nhiều năm: mỗi năm một phần
    per_year_hits = [_query(cfg, question, w, per) for w in wheres]
    hits = _group_balanced(per_year_hits, k)

    if plan.mode == "latest" and not hits:
        # chỉ mục cũ chưa có cờ latest_in_topic: truy vấn rộng hơn nhưng tránh bản đã bị thay thế / không rõ năm
        raw_hits = _query(cfg, question, None, max(k * 2, k))
        non_sup = [h for h in raw_hits if h.get("metadata", {}).get("is_superseded", 0) != 1]
        known_yr = [h for h in (non_sup or raw_hits) if h.get("metadata", {}).get("start_year")]
        hits = (known_yr or non_sup or raw_hits)[:k]
        plan = VersionPlan("latest", None, plan.reason + " (chưa có cờ latest_in_topic: chạy lại index)")

    if plan.mode == "latest" and hits:
        # Lọc an toàn: ưu tiên các bản không bị đánh dấu superseded và có năm học xác định
        clean = [
            h for h in hits
            if h.get("metadata", {}).get("is_superseded", 0) != 1 and h.get("metadata", {}).get("start_year")
        ]
        if clean:
            hits = clean

    # câu hỏi nêu rõ "Điều N": ưu tiên các chunk đúng Điều đó (trong cùng bộ lọc phiên bản)
    art = extract_article(question)
    if art:
        art_lists = [_query(cfg, question, _and(w, {"dieu_so": art}), 2) for w in wheres]
        art_hits = _group_balanced(art_lists, 2)
        seen = {h["document"] for h in art_hits}
        hits = (art_hits + [h for h in hits if h["document"] not in seen])[:k]

    if plan.mode == "latest" and hits:
        years = sorted({h["metadata"]["start_year"] for h in hits if h["metadata"].get("start_year")}, reverse=True)
        if years:
            plan = VersionPlan("latest", years[0],
                               "không nêu năm -> văn bản mới nhất của từng chủ đề", tuple(years))
    return hits, plan
