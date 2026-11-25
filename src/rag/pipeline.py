"""Main entry point for ChronoReg RAG pipeline: answer(question, as_of_year, mode) -> dict."""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from .config import load_config
from .eval_adapter import RAGEvalAdapter, detect_topic

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_cfg: dict[str, Any] | None = None
_adapter: RAGEvalAdapter | None = None


def _get_adapter() -> RAGEvalAdapter:
    global _adapter
    if _adapter is None:
        _adapter = RAGEvalAdapter()
    return _adapter


def _clean_display_answer(text: str) -> str:
    """Remove repeated synthetic cohort tags for cleaner human CLI display."""
    s = re.sub(r"(?:\s*\((?:khóa\s+)?QH-20[12]\d\))+", "", text, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" ;")
    return s


def answer(
    question: str,
    as_of_year: int | None = None,
    mode: str = "chrono_rag",
    cfg: dict[str, Any] | None = None,
    backend: str = "bm25",
    clean_display: bool = False,
    embed_fn: Any = None,
    llm_fn: Any = None,
) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string.")
    if mode not in ("chrono_rag", "chrono_rag_llm", "naive_rag"):
        raise ValueError(f"Unsupported mode: {mode}. Expected 'chrono_rag', 'chrono_rag_llm', or 'naive_rag'.")
    if backend not in ("bm25", "hybrid"):
        raise ValueError(f"Unsupported backend: {backend}. Expected 'bm25' or 'hybrid'.")

    adapter = _get_adapter()
    item = {"id": "RUNTIME_QUERY", "question": question.strip()}
    use_cfg = cfg if cfg is not None else load_config()
    top_k = int((use_cfg or {}).get("top_k", 4) or 4)
    preds = adapter.run_benchmark(
        [item],
        mode=mode,
        top_k=top_k,
        as_of_year=as_of_year,
        backend=backend,
        embed_fn=embed_fn,
        llm_fn=llm_fn,
        cfg=use_cfg,
    )
    res = preds[0]

    pred_year = res.get("as_of_year")
    ay_label = f"{pred_year}-{pred_year + 1}" if isinstance(pred_year, int) and pred_year > 0 else ""
    inferred_cat = res.get("inferred_category", "")
    inferred_topic = detect_topic(question)

    # Deduplicate sources by doc_id
    enriched_sources: list[dict[str, Any]] = []
    seen_docs: set[str] = set()
    for src in res.get("sources", []):
        did = src.get("doc_id") or ""
        if not did or did in seen_docs:
            continue
        seen_docs.add(did)
        d_meta = adapter.retriever.doc_meta.get(did, {})
        enriched_sources.append({
            "doc_id": did,
            "dieu_so": src.get("dieu_so") or "",
            "academic_year": src.get("academic_year") or d_meta.get("academic_year", ay_label),
            "year_status": "verified" if d_meta.get("retrieval_eligible", True) else "unverified",
            "review_status": "verified_against_source" if d_meta.get("retrieval_eligible", True) else "needs_human_review",
            "topic": d_meta.get("topic") or inferred_topic,
            "source_path": d_meta.get("source_path", "data/raw/uet/markdown/Thoi_khoa_bieu_hoc_ki_I_2022_2023.md"),
        })

    if not inferred_topic and enriched_sources:
        inferred_topic = enriched_sources[0]["topic"]

    raw_ans = res["predicted_answer"]
    final_ans = _clean_display_answer(raw_ans) if clean_display else raw_ans

    return {
        "answer": final_ans,
        "predicted_answer": raw_ans,
        "prediction": raw_ans,
        "as_of_year": pred_year,
        "sources": enriched_sources,
        "cited_doc_ids": res.get("cited_doc_ids", []),
        "unreviewed_sources": res.get("unreviewed_sources", []),
        "llm_used": bool(res.get("llm_used", False)),
        "latency_ms": res.get("latency_ms", 0.0),
        "mode": mode,
        "debug": {
            "backend": f"{backend}_v9",
            "mode": inferred_cat,
            "topic": inferred_topic,
            "academic_year": ay_label,
            "llm_used": bool(res.get("llm_used", False)),
            "reason": f"category={inferred_cat}, topic={inferred_topic or 'all'}, start_year={pred_year}",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ChronoReg RAG Question Answering CLI")
    ap.add_argument("question", help="Câu hỏi quy chế cần tra cứu")
    ap.add_argument("--year", type=int, default=None, help="Năm bắt đầu của năm học (vd: 2024 cho 2024-2025)")
    ap.add_argument("--mode", choices=["chrono_rag", "chrono_rag_llm", "naive_rag"], default="chrono_rag")
    ap.add_argument("--backend", choices=["bm25", "hybrid"], default="bm25")
    ap.add_argument("--json", action="store_true", help="Xuất kết quả dạng JSON")
    args = ap.parse_args(argv)

    out = answer(args.question, args.year, mode=args.mode, backend=args.backend, clean_display=True)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("Debug  :", out["debug"])
    print("Sources:")
    for s in out["sources"]:
        dieu_tag = f", {s['dieu_so']}" if s.get("dieu_so") else ""
        print(f"  - {s['doc_id']} ({s['academic_year']}{dieu_tag}) [{s['topic']}]")
    print("\nAnswer :")
    print(out["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())