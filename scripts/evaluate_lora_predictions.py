"""Evaluate real V3 prediction JSONL against the project benchmark without altering it.

Usage: python scripts/evaluate_lora_predictions.py --benchmark data/qa_benchmark/benchmark.jsonl \
          --predictions /path/to/live_predictions.jsonl --output result.json

This is a diagnostic; exact match is not equivalent to semantic correctness.
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


def normalize(text):
    return " ".join(re.findall(r"\w+", str(text).casefold(), flags=re.UNICODE))


def score(benchmark: Path, predictions: Path) -> dict:
    bench_bytes = benchmark.read_bytes()
    ground = [json.loads(x) for x in bench_bytes.decode("utf-8").splitlines() if x.strip()]
    guesses = [json.loads(x) for x in predictions.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len({x["id"] for x in ground}) != len(ground):
        raise ValueError("Duplicate benchmark IDs")
    if len({x["id"] for x in guesses}) != len(guesses):
        raise ValueError("Duplicate prediction IDs")
    gold_by_id = {x["id"]: x for x in ground}
    if not set(x["id"] for x in guesses) <= set(gold_by_id):
        raise ValueError("Unknown prediction IDs")
    for row in guesses:
        if row.get("engine_mode") != "LIVE_PEFT_GENERATION":
            raise ValueError("Refusing replayed or non-live LoRA predictions")
        if row.get("checkpoint_year") != 2026:
            raise ValueError("Expected final checkpoint 2026 for fair comparison")
    pred_by_id = {x["id"]: x for x in guesses}
    by_bucket = defaultdict(lambda: {"count": 0, "answered": 0, "exact": 0})
    details = []
    for g in ground:
        p = pred_by_id.get(g["id"])
        cat = str(g.get("type") or g.get("category") or "unknown")
        prediction = p.get("prediction", "") if p else ""
        gold = g.get("gold_answer") or g.get("ground_truth_answer") or ""
        answered = bool(str(prediction).strip())
        exact = answered and normalize(prediction) == normalize(gold)
        by_bucket[cat]["count"] += 1
        by_bucket[cat]["answered"] += int(answered)
        by_bucket[cat]["exact"] += int(exact)
        details.append({"id": g["id"], "category": cat, "answered": answered,
                        "exact_normalized": bool(exact), "prediction": prediction,
                        "gold_answer": gold})
    n = len(ground)
    matched = sum(row["exact_normalized"] for row in details)
    return {"status": "DIAGNOSTIC_NOT_CERTIFIED", "benchmark_sha256":
        hashlib.sha256(bench_bytes).hexdigest(),
        "scope": "V3 final adapter, evaluation questions not necessarily human-approved",
        "benchmark_count": n, "predictions_count": len(guesses),
        "coverage": len(guesses) / n if n else 0,
        "normalized_exact_count": matched,
        "normalized_exact_rate_all": matched / n if n else 0,
        "metrics_note": "Exact match only; requires manual fact correctness and temporal/outdated review",
        "by_category": dict(by_bucket), "details": details}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stats = score(args.benchmark, args.predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("details", "by_category")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
