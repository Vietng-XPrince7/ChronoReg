"""Strict, standalone smoke test for the **actual** ChronoReg V3 PEFT checkpoint.

Does not load stored predictions, does not touch RAG or StudentHub routing, and
never labels a generated response as verified academic regulations.

File readiness (no GPU):
    python scripts/lora_live_smoke.py --preflight
GPU live inference (use CUDA_VISIBLE_DEVICES=0 BEFORE the Python process):
    python scripts/lora_live_smoke.py --live --question "Học phí học kỳ này được quy định thế nào?" --report lora_smoke.json
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.lora.runtime_setup import default_models_root, ensure_base_model
from src.lora.verified_v3 import BASE_REVISION, VerifiedV3Inference, verify_v3


def installed_versions() -> dict[str, str | None]:
    packages = ("torch", "transformers", "peft", "bitsandbytes", "accelerate")
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def file_preflight(models_root: Path) -> dict:
    adapter_dir = models_root / "chronoreg-v3"
    # These MUST raise for missing or tampered adapters.
    verified = verify_v3(adapter_dir)
    base = ensure_base_model(models_root, download=False)
    ready_files = base["status"] != "BASE_MISSING"
    return {
        "status": "FILES_READY_NOT_INFERENCE_TESTED" if ready_files else "BASE_MISSING",
        "artifact_integrity": verified["status"],
        "trained_years": verified["years"],
        "training_qa": sum(stage["training_rows"] for stage in verified["checkpoints"]),
        "final_adapter_sha256": verified["checkpoints"][-1]["sha256"],
        "base_revision_expected": BASE_REVISION,
        "base_revision_verified": base["revision_verified"],
        "base_model_present": ready_files,
        "live_inference_tested": False,
        "quality_qualified": False,
        "scope": verified["scope"],
        "versions": installed_versions(),
    }


def run_live(models_root: Path, question: str, year: int, as_of_year: int | None) -> dict:
    if not question.strip():
        raise ValueError("Empty question")
    preflight = file_preflight(models_root)
    if not preflight["base_model_present"]:
        raise RuntimeError("BASE_MISSING: first install pinned Qwen base via scripts/setup_lora_v3.py --download-base")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA_REQUIRED: live smoke requires GPU; no cached-answer fallback")
    if torch.cuda.device_count() != 1:
        raise RuntimeError("SINGLE_GPU_REQUIRED: set CUDA_VISIBLE_DEVICES=0 before launching Python")
    model = VerifiedV3Inference(models_root / "chronoreg-v3",
                                models_root / "Qwen2.5-3B-Instruct", year=year)
    result = model.generate(question, as_of_year=as_of_year)
    if result.get("engine_mode") != "LIVE_PEFT_GENERATION" or not result.get("answer", "").strip():
        raise RuntimeError("LIVE_PEFT_SMOKE_FAILED: blank or non-live model response")
    return {
        **preflight,
        "status": "LIVE_PEFT_SMOKE_PASS_NOT_QUALITY_CERTIFICATION",
        "live_inference_tested": True,
        "checkpoint_year": year,
        "requested_year": as_of_year,
        "question": question,
        "model_output": result["answer"],
        "latency_ms": result["latency_ms"],
        "engine_mode": result["engine_mode"],
        "quality_qualified": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="ChronoReg LoRA-only live PEFT smoke, never an accuracy certificate")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="SHA and local base check, no GPU")
    mode.add_argument("--live", action="store_true", help="Generate an answer with the REAL PEFT adapter")
    p.add_argument("--models-root", type=Path, default=default_models_root(ROOT))
    p.add_argument("--question", default="Học phí được quy định như thế nào trong năm học 2026-2027?")
    p.add_argument("--checkpoint-year", type=int, choices=range(2022, 2027), metavar="2022..2026", default=2026)
    p.add_argument("--as-of-year", type=int, choices=range(2022, 2027), metavar="2022..2026", default=None)
    p.add_argument("--report", type=Path, help="Output JSON report, must not already exist")
    args = p.parse_args()
    if args.report and args.report.exists():
        p.error("Report already exists; refusing to overwrite")
    try:
        data = (run_live(args.models_root, args.question, args.checkpoint_year, args.as_of_year)
                if args.live else file_preflight(args.models_root))
        code = 0 if data["status"] != "BASE_MISSING" else 2
    except Exception as exc:
        data = {"status": "FAILED", "reason": str(exc), "live_inference_tested": False,
                "quality_qualified": False}
        code = 1
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
