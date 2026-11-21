"""Runs real LoRA V3 inference on benchmark questions; never passes gold to model.

Requires a local Qwen2.5-3B-Instruct base-model snapshot + extracted V3 adapters.
Use a *fresh* single-GPU process (CUDA_VISIBLE_DEVICES=0).
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lora.verified_v3 import VerifiedV3Inference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=192)
    args = parser.parse_args()
    rows = [json.loads(x) for x in args.benchmark.read_text(encoding="utf-8").splitlines() if x.strip()]
    adapter = VerifiedV3Inference(args.artifact_dir, args.base_dir, year=2026,
                                   max_new_tokens=args.max_new_tokens)
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    observed = set()
    # Resume only if file is live-only and every prior prediction is for this benchmark.
    if args.predictions.exists():
        previous = [json.loads(x) for x in args.predictions.read_text(encoding="utf-8").splitlines() if x.strip()]
        goldids = {r["id"] for r in rows}
        for p in previous:
            if p.get("engine_mode") != "LIVE_PEFT_GENERATION" or p.get("id") not in goldids:
                raise ValueError("Non-live or foreign predictions in output; refusing to append")
            if p.get("id") in observed:
                raise ValueError("Duplicate cached prediction ID")
            observed.add(p["id"])
    with args.predictions.open("a", encoding="utf-8") as f:
        for i, item in enumerate(rows, 1):
            if item["id"] in observed:
                continue
            result = adapter.generate(item["question"], as_of_year=item.get("as_of_year"))
            rec = {"id": item["id"], "prediction": result["answer"],
                   "engine_mode": "LIVE_PEFT_GENERATION", "checkpoint_year": 2026,
                   "as_of_year": item.get("as_of_year"), "latency_ms": result["latency_ms"]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{i}/{len(rows)} ID={item['id']} LIVE_PEFT_GENERATION", flush=True)
    print("LIVE_BENCHMARK_PREDICTIONS_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
