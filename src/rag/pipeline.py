"""Điểm vào của RAG: answer(question, as_of_year) -> {"answer", "sources"}.

Cùng chữ ký với phía LoRA để src/eval/ chạy được cho cả hai.
Thử nhanh:  python -m src.rag.pipeline "Điều kiện tốt nghiệp?" --year 2022
"""
from __future__ import annotations

import argparse

from .config import load_config
from .generate import fmt_ts, generate
from .retrieve import retrieve
from .versioning import plan_version

_cfg: dict | None = None


def answer(question: str, as_of_year: int | None = None) -> dict:
    global _cfg
    _cfg = _cfg or load_config()
    plan = plan_version(question, as_of_year, _cfg.get("year_to_date", "12-31"))
    hits = retrieve(question, plan, _cfg)

    if not hits:
        text = "Không tìm thấy quy định phù hợp có hiệu lực tại thời điểm được hỏi."
    else:
        text = generate(question, hits, plan, _cfg)

    sources = [{
        "doc_id": h["metadata"]["doc_id"],
        "dieu_so": h["metadata"]["dieu_so"],
        "title": h["metadata"]["title"],
        "effective_date": fmt_ts(h["metadata"]["effective_ts"]),
        "expired_date": None if h["metadata"]["expired_ts"] == 99991231
        else fmt_ts(h["metadata"]["expired_ts"]),
    } for h in hits]
    # "debug" là trường phụ để kiểm tra việc chọn phiên bản; bỏ đi nếu eval không cần.
    return {"answer": text, "sources": sources,
            "debug": {"mode": plan.mode, "t": plan.t, "reason": plan.reason}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--year", type=int, default=None)
    a = ap.parse_args()
    out = answer(a.question, a.year)
    print(out["debug"])
    print([f"{s['doc_id']} {s['dieu_so']}" for s in out["sources"]])
    print(out["answer"])
