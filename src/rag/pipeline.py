"""Điểm vào của RAG: answer(question, as_of_year) -> {"answer", "sources"}.

Cùng chữ ký với phía LoRA để src/eval/ chạy được cho cả hai.
Thử nhanh:  python -m src.rag.pipeline "Học phí năm học 2023-2024 là bao nhiêu?"
"""
from __future__ import annotations

import argparse

from .config import load_config
from .generate import generate
from .retriever import retrieve
from .versioning import plan_version

_cfg: dict | None = None


def answer(question: str, as_of_year: int | None = None) -> dict:
    global _cfg
    _cfg = _cfg or load_config()
    plan = plan_version(question, as_of_year, _cfg.get("single_year_means", "start"))
    hits, plan = retrieve(question, plan, _cfg)

    if not hits:
        text = "Không tìm thấy quy định phù hợp với năm học được hỏi."
    else:
        text = generate(question, hits, plan, _cfg)

    sources = [{
        "doc_id": h["metadata"]["doc_id"],
        "academic_year": h["metadata"]["academic_year"],
        "year_status": h["metadata"]["year_status"],
        "review_status": h["metadata"]["review_status"],
        "topic": h["metadata"]["topic_hint"],
    } for h in hits]
    # "debug" là trường phụ để kiểm tra việc chọn phiên bản; bỏ đi nếu eval không cần.
    return {"answer": text, "sources": sources,
            "debug": {"mode": plan.mode, "academic_year": plan.label(), "reason": plan.reason}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--year", type=int, default=None)
    a = ap.parse_args()
    out = answer(a.question, a.year)
    print(out["debug"])
    for s in out["sources"]:
        print(" -", s["doc_id"], s["academic_year"], s["year_status"])
    print(out["answer"])
