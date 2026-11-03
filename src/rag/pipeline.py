"""Điểm vào của RAG: answer(question, as_of_year, mode) -> dict.

Hỗ trợ 2 chế độ đánh giá:
- "chrono_rag": Nhận diện phiên bản, năm học và quy định thay thế
- "naive_rag": Truy xuất thuần ngữ nghĩa, không lọc phiên bản

Cùng chữ ký và prediction schema tương thích với src/lora/ và src/eval/.
"""
from __future__ import annotations

import argparse

from .config import load_config
from .generate import generate
from .retriever import retrieve
from .versioning import VersionPlan, plan_version

_cfg: dict | None = None


def answer(
    question: str,
    as_of_year: int | None = None,
    mode: str = "chrono_rag",
    cfg: dict | None = None,
) -> dict:
    """Trả lời câu hỏi bằng RAG pipeline.

    Args:
        question: Câu hỏi người dùng.
        as_of_year: Năm học cần tra cứu (tùy chọn).
        mode: "chrono_rag" (nhận diện phiên bản) hoặc "naive_rag" (không lọc phiên bản).
        cfg: Cấu hình RAG (tùy chọn, mặc định nạp từ configs/rag.yaml).

    Returns:
        dict chứa {answer, predicted_answer, prediction, sources, cited_doc_ids, mode, debug}
    """
    global _cfg
    current_cfg = cfg or _cfg or load_config()

    if mode == "naive_rag":
        plan = VersionPlan(mode="all", start_year=None, reason="naive_rag: không lọc phiên bản")
        hits, plan = retrieve(question, plan, current_cfg)
    else:
        plan = plan_version(question, as_of_year, current_cfg.get("single_year_means", "start"))
        hits, plan = retrieve(question, plan, current_cfg)

    if not hits:
        text = "Không tìm thấy quy định phù hợp với năm học được hỏi."
    else:
        text = generate(question, hits, plan, current_cfg)

    sources = [{
        "doc_id": h["metadata"]["doc_id"],
        "academic_year": h["metadata"]["academic_year"],
        "year_status": h["metadata"]["year_status"],
        "review_status": h["metadata"]["review_status"],
        "topic": h["metadata"]["topic_hint"],
    } for h in hits]
    cited_doc_ids = [s["doc_id"] for s in sources]

    return {
        "answer": text,
        "predicted_answer": text,
        "prediction": text,
        "sources": sources,
        "cited_doc_ids": cited_doc_ids,
        "mode": mode,
        "debug": {"mode": plan.mode, "academic_year": plan.label(), "reason": plan.reason},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--mode", choices=["chrono_rag", "naive_rag"], default="chrono_rag")
    a = ap.parse_args()
    out = answer(a.question, a.year, mode=a.mode)
    print(out["debug"])
    for s in out["sources"]:
        print(" -", s["doc_id"], s["academic_year"], s["year_status"])
    print(out["answer"])
