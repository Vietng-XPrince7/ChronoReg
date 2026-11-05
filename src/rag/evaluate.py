"""Đo RAG trên bộ câu hỏi của Việt ở mức TRUY XUẤT (chưa cần LLM).

Chạy:
  python -m src.rag.evaluate                    # as_of_year không truyền: chỉ dựa vào năm trong câu hỏi
  python -m src.rag.evaluate --as-of target     # truyền as_of_year = target_year của từng câu
  python -m src.rag.evaluate --out ket_qua.json # lưu chi tiết từng câu

Các chỉ số (đều là chỉ số truy xuất, KHÔNG thay cho version accuracy / outdated-answer rate
tính trên câu trả lời của LLM trong src/eval/ của Việt):
  hit@k      văn bản gốc (source_doc_id) có nằm trong k kết quả không
  hit@1      kết quả đầu tiên có phải văn bản gốc không
  top1 đúng/cũ/mới   năm học của kết quả đầu so với target_year
             (câu superseded_rule chấp nhận cả target_year và target_year+1)
  fact recall  tỉ lệ các số tiền/số liệu trong key_facts xuất hiện trong văn bản truy xuất được
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict

from . import store
from .config import load_config, resolve
from .retriever import retrieve
from .versioning import plan_version

_NUM = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")


def numbers(text: str) -> set[str]:
    return {re.sub(r"[.,]", "", t) for t in _NUM.findall(text)}


def numeric_facts(facts: list[str]) -> set[str]:
    """Các số liệu đáng so khớp trong key_facts (bỏ số ngắn và số giống năm như 2022)."""
    out = set()
    for f in facts:
        for t in numbers(f):
            if len(t) >= 4 and not (len(t) == 4 and t[:2] in ("19", "20")):
                out.add(t)
    return out


def fact_recall(facts: list[str], context: str) -> float | None:
    need = numeric_facts(facts)
    return len(need & numbers(context)) / len(need) if need else None


def expected_years(item: dict) -> set[int]:
    y = item.get("target_year")
    if not y:
        return set()
    return {y, y + 1} if item.get("category") == "superseded_rule" else {y}


def top1_status(hits: list[dict], exp: set[int]) -> str:
    if not hits:
        return "no_result"
    y = hits[0]["metadata"]["start_year"]
    if not y:
        return "unknown_year"
    if not exp:
        return "n/a"
    return "correct" if y in exp else ("outdated" if y < min(exp) else "too_new")


def evaluate(items: list[dict], cfg: dict, as_of_mode: str = "none") -> list[dict]:
    indexed = {m["doc_id"] for m in store.get_collection(cfg).get(include=["metadatas"])["metadatas"]}
    rows = []
    for it in items:
        as_of = it.get("target_year") if as_of_mode == "target" else None
        plan = plan_version(it["question"], as_of, cfg.get("single_year_means", "start"))
        hits, plan = retrieve(it["question"], plan, cfg)
        docs = [h["metadata"]["doc_id"] for h in hits]
        gold = it.get("source_doc_id")
        rows.append({
            "id": it.get("id"), "category": it.get("category", "?"), "mode": plan.mode,
            "plan": plan.reason, "gold_doc": gold, "gold_indexed": gold in indexed,
            "hit_any": gold in docs, "hit_1": bool(docs) and docs[0] == gold,
            "top1": top1_status(hits, expected_years(it)),
            "top1_doc": docs[0] if docs else None,
            "top1_year": hits[0]["metadata"]["academic_year"] if hits else None,
            "recall": fact_recall(it.get("key_facts") or [], "\n".join(h["document"] for h in hits)),
            "question": it["question"],
        })
    return rows


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%" if d else "   -  "


def summarize(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["category"]].append(r)
        groups["TỔNG"].append(r)
    out = {}
    for cat, rs in groups.items():
        idx = [r for r in rs if r["gold_indexed"]]
        rec = [r["recall"] for r in rs if r["recall"] is not None]
        t = Counter(r["top1"] for r in rs)
        out[cat] = {
            "n": len(rs), "gold_not_indexed": len(rs) - len(idx),
            "hit@k": sum(r["hit_any"] for r in rs) / len(rs),
            "hit@k_indexed_only": (sum(r["hit_any"] for r in idx) / len(idx)) if idx else None,
            "hit@1": sum(r["hit_1"] for r in rs) / len(rs),
            "top1": dict(t),
            "fact_recall": (sum(rec) / len(rec)) if rec else None,
        }
    return out


def print_report(rows: list[dict], show: int = 8) -> None:
    summ = summarize(rows)
    print(f"{'nhóm':<18}{'n':>4}{'chưa-index':>11}{'hit@k':>8}{'hit@k*':>8}{'hit@1':>8}"
          f"{'top1 đúng':>11}{'cũ':>7}{'mới':>7}{'?năm':>7}{'recall':>8}")
    for cat, s in sorted(summ.items(), key=lambda kv: (kv[0] == "TỔNG", kv[0])):
        t, n = s["top1"], s["n"]
        rec = f"{100 * s['fact_recall']:5.1f}%" if s["fact_recall"] is not None else "   -  "
        hk = _pct(round(s["hit@k"] * n), n)
        hks = f"{100 * s['hit@k_indexed_only']:5.1f}%" if s["hit@k_indexed_only"] is not None else "   -  "
        print(f"{cat:<18}{n:>4}{s['gold_not_indexed']:>11}{hk:>8}{hks:>8}{_pct(round(s['hit@1'] * n), n):>8}"
              f"{_pct(t.get('correct', 0), n):>11}{_pct(t.get('outdated', 0), n):>7}"
              f"{_pct(t.get('too_new', 0), n):>7}{_pct(t.get('unknown_year', 0) + t.get('no_result', 0), n):>7}{rec:>8}")
    print("\n(hit@k* chỉ tính câu mà văn bản gốc có trong chỉ mục; recall = số liệu key_facts tìm thấy)")
    bad = [r for r in rows if r["gold_indexed"] and not r["hit_any"]]
    print(f"\nCâu có văn bản gốc trong chỉ mục nhưng không truy xuất được: {len(bad)}")
    for r in bad[:show]:
        print(f" - {r['id']} [{r['category']}] {r['question'][:70]}...")
        print(f"     {r['plan']} | top1: {(r['top1_doc'] or '-')[:48]} {r['top1_year'] or ''} | gốc: {r['gold_doc'][:48]}")
    miss = Counter(r["gold_doc"] for r in rows if not r["gold_indexed"])
    if miss:
        print(f"\nVăn bản gốc CHƯA có trong chỉ mục ({len(miss)} văn bản, {sum(miss.values())} câu):")
        for d, c in miss.most_common(show):
            print(f" - {c:>2} câu: {d}")


def load_items(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="data/qa_benchmark/benchmark.jsonl")
    ap.add_argument("--as-of", choices=["none", "target"], default="none")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None, help="lưu chi tiết từng câu (JSON)")
    ap.add_argument("--show", type=int, default=8)
    a = ap.parse_args()
    cfg = load_config()
    items = load_items(resolve(a.bench))[: a.limit]
    print(f"{len(items)} câu | chunks_file={cfg['chunks_file']} | as_of={a.as_of} | top_k={cfg.get('top_k', 5)}\n")
    rows = evaluate(items, cfg, a.as_of)
    print_report(rows, a.show)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"summary": summarize(rows), "rows": rows}, f, ensure_ascii=False, indent=1)
