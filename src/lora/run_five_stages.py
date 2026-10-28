"""Release-bound five-stage LoRA training and held-out evaluation.

Fail closed. No synthetic data, no approval generation, no automatic model pins.
A completed run is not evidence of factual correctness without human review.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .contracts import read_jsonl, sha256
from .modeling import check_previous, train_stage, LoRAAnswerer
from .evaluate import evaluate_stages
from .release_guard import require_training_release

YEARS = [2022, 2023, 2024, 2025, 2026]
PINNED_REV = re.compile(r"^[0-9a-f]{40}$")


def load_config(config_file: Path) -> dict:
    import yaml
    data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    cfg = data["lora"]
    if cfg.get("strategy") != "sequential" or cfg.get("years") != YEARS:
        raise RuntimeError("Expected chronological five-stage LoRA years 2022-2026")
    if cfg.get("base_model") != "Qwen/Qwen2.5-0.5B-Instruct":
        raise RuntimeError("Expected the validated Qwen2.5-0.5B-Instruct baseline")
    if cfg.get("model_dtype") != "float32" or cfg.get("max_seq_length") != 512:
        raise RuntimeError("Only the stress-tested FP32 / 512-token configuration is supported")
    return cfg


def check_pin(cfg: dict) -> None:
    if not PINNED_REV.fullmatch(str(cfg.get("model_revision") or "")):
        raise RuntimeError("MODEL_REVISION_NOT_PINNED: pin a verified 40-character Hugging Face SHA before live training")


def _run_config_sha256(cfg: dict) -> str:
    """Bind resumed adapters to the same exact training and inference settings."""
    encoded = json.dumps(cfg, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _released_benchmark(repo: Path, cfg: dict, expected_sha256: str) -> Path:
    """Reject a different or modified evaluation benchmark before GPU allocation."""
    relative = cfg.get("benchmark", "data/qa_benchmark/benchmark.jsonl")
    if not isinstance(relative, str) or not relative.strip():
        raise RuntimeError("BENCHMARK_PATH_INVALID: expected repository-relative benchmark")
    path = Path(relative)
    if path.is_absolute():
        raise RuntimeError("BENCHMARK_PATH_INVALID: absolute path refused")
    canonical = (repo / path).resolve()
    if not canonical.is_relative_to(repo.resolve()) or not canonical.is_file():
        raise RuntimeError("BENCHMARK_PATH_INVALID: missing or outside repository")
    if sha256(canonical) != expected_sha256:
        raise RuntimeError("BENCHMARK_MISMATCH_BEFORE_TRAINING: configured benchmark does not match the owner release")
    return canonical


def _save_integrity(checkpoints: Path, year: int, release_file_hash: str, cfg: dict) -> None:
    """Commit saved adapter bytes and full run configuration to a checksum sidecar."""
    folder = checkpoints / f"year-{year}"
    sidecar = folder / "adapter_integrity.json"
    if sidecar.exists():
        raise FileExistsError(f"REFUSE_TO_REWRITE_INTEGRITY: {sidecar}")
    hashes = {name: sha256(folder / name) for name in
              ("adapter_model.safetensors", "adapter_config.json", "stage.json")}
    record = {"schema": "chronoreg-adapter-integrity/v2", "year": year,
              "release_file_sha256": release_file_hash,
              "run_config_sha256": _run_config_sha256(cfg), "file_sha256": hashes}
    sidecar.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _stage_info(checkpoints: Path, year: int, cfg: dict, manifest: dict,
                release_file_hash: str) -> dict | None:
    folder = checkpoints / f"year-{year}"
    if not folder.exists():
        return None
    if not folder.is_dir() or folder.is_symlink():
        raise RuntimeError(f"UNSAFE_EXISTING_CHECKPOINT: {folder}")
    meta = folder / "stage.json"
    weights = folder / "adapter_model.safetensors"
    config = folder / "adapter_config.json"
    if not all(p.is_file() for p in (meta, weights, config)) or weights.stat().st_size <= 0:
        raise RuntimeError(f"INCOMPLETE_EXISTING_CHECKPOINT: {folder}")
    sidecar = folder / "adapter_integrity.json"
    if not sidecar.is_file():
        raise RuntimeError(f"MISSING_CHECKPOINT_INTEGRITY: {folder}")
    binding = json.loads(sidecar.read_text(encoding="utf-8"))
    if (binding.get("schema") != "chronoreg-adapter-integrity/v2"
            or binding.get("run_config_sha256") != _run_config_sha256(cfg)
            or binding.get("year") != year
            or binding.get("release_file_sha256") != release_file_hash
            or any(binding.get("file_sha256", {}).get(name) != sha256(folder / name)
                   for name in ("adapter_model.safetensors", "adapter_config.json", "stage.json"))):
        raise RuntimeError(f"CHECKPOINT_INTEGRITY_MISMATCH: {folder}")
    info = json.loads(meta.read_text(encoding="utf-8"))
    if (info.get("year") != year or info.get("model") != cfg["base_model"]
            or info.get("model_revision") != cfg["model_revision"]
            or info.get("model_dtype") != cfg["model_dtype"]
            or info.get("training_sha256") != manifest["year_sha256"][str(year)]
            or info.get("release_evidence", {}).get("release_file_sha256") != release_file_hash):
        raise RuntimeError(f"STALE_OR_UNRELEASED_CHECKPOINT: {folder}")
    return info


def preflight(repo: Path, cfg: dict, release: Path,
              prepared: Path, checkpoints: Path) -> dict:
    """No Torch/model imports. Validates every stage before any execution."""
    check_pin(cfg)
    if not prepared.is_dir():
        raise RuntimeError(f"PREPARED_MISSING: {prepared}")
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("years") != YEARS or manifest.get("total", 0) < 1:
        raise RuntimeError("INVALID_PREPARED_MANIFEST: five ordered stages required")
    if any(not isinstance(manifest.get("counts", {}).get(str(y)), int)
           or manifest["counts"][str(y)] < 1 for y in YEARS):
        raise RuntimeError("EMPTY_TRAINING_STAGE: a reviewed QA is required for every year")
    for year in YEARS:
        data = prepared / f"train_{year}.jsonl"
        if not data.is_file() or sha256(data) != manifest["year_sha256"].get(str(year)):
            raise RuntimeError(f"STAGED_QA_HASH_INVALID: {year}")
    # Release guard validates benchmark, full 90-case freeze and fact-level leakage ledger.
    releases = [require_training_release(repo, prepared, year, release) for year in YEARS]
    if any(x != releases[0] for x in releases):
        raise RuntimeError("INCONSISTENT_STAGE_RELEASE")
    release_hash = releases[0]["release_file_sha256"]
    # The release guard may allow a repository-relative benchmark path that is
    # different from cfg['benchmark']; catch it now, not after five GPU stages.
    _released_benchmark(repo, cfg, releases[0]["benchmark_sha256"])
    state = []
    seen_missing = False
    for year in YEARS:
        info = _stage_info(checkpoints, year, cfg, manifest, release_hash)
        if info is None:
            state.append({"year": year, "status": "PENDING"})
            seen_missing = True
        else:
            if seen_missing:
                raise RuntimeError("CHECKPOINT_CHAIN_HAS_GAP: cannot resume out of order")
            if year > YEARS[0]:
                check_previous(checkpoints / f"year-{year-1}", year, cfg)
            state.append({"year": year, "status": "VERIFIED_EXISTING"})
    return {"status": "READY_FOR_RELEASED_EXECUTION", "stages": state,
            "release_sha256": release_hash, "training_total": manifest["total"],
            "run_config_sha256": _run_config_sha256(cfg),
            "benchmark_sha256": releases[0]["benchmark_sha256"],
            "model_revision": cfg["model_revision"], "production_training_authorized": True}


def _clear_gpu() -> None:
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def execute(repo: Path, cfg: dict, release: Path, prepared: Path,
            checkpoints: Path, results: Path, *, resume: bool = False) -> dict:
    plan = preflight(repo, cfg, release, prepared, checkpoints)
    already = [x for x in plan["stages"] if x["status"] == "VERIFIED_EXISTING"]
    if already and not resume:
        raise RuntimeError("CHECKPOINTS_ALREADY_EXIST: use --resume after verifying saved adapters")
    if results.exists():
        raise FileExistsError(f"REFUSE_TO_OVERWRITE_RESULTS: {results}")
    year_runs = []
    for item in plan["stages"]:
        year = item["year"]
        if item["status"] == "VERIFIED_EXISTING":
            year_runs.append({"year": year, "status": "REUSED_VERIFIED_CHECKPOINT"})
            continue
        previous = checkpoints / f"year-{year-1}" if year > YEARS[0] else None
        outcome = train_stage(cfg, prepared, year, checkpoints, previous=previous,
                              repo=repo, release_path=release, dry_run=False)
        # A stage is only accepted if the model code wrote a complete, release-bound adapter.
        manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
        _save_integrity(checkpoints, year, plan["release_sha256"], cfg)
        _stage_info(checkpoints, year, cfg, manifest, plan["release_sha256"])
        year_runs.append({"year": year, "status": "TRAINED_AND_VERIFIED",
                          "training_rows": outcome["training_rows"]})
        _clear_gpu()
    # Do not create evaluation files until all five stage checkpoints are verified.
    if any(not (checkpoints / f"year-{y}" / "stage.json").is_file() for y in YEARS):
        raise RuntimeError("MISSING_STAGE: evaluation refused")
    current = {"year": None, "answerer": None}
    def predict(stage: int, question: str, as_of_year: int) -> str:
        if current["year"] != stage:
            current["answerer"] = None
            _clear_gpu()
            current["answerer"] = LoRAAnswerer(cfg, checkpoints / f"year-{stage}", allow_cpu=False)
            current["year"] = stage
        return current["answerer"].answer(question, as_of_year)["answer"]
    # Recheck after training to detect a benchmark modified during execution.
    bench = _released_benchmark(repo, cfg, plan["benchmark_sha256"])
    scoring = evaluate_stages(bench, YEARS, predict, results)
    current["answerer"] = None
    _clear_gpu()
    report = {"status": "FIVE_STAGE_RUN_COMPLETE_NOT_HUMAN_ADJUDICATED",
              "stages": year_runs, "release_sha256": plan["release_sha256"],
              "benchmark_sha256": plan["benchmark_sha256"], "base_model": cfg["base_model"],
              "model_revision": cfg["model_revision"],
              "run_config_sha256": plan["run_config_sha256"],
              "unique_benchmark_cases": scoring["unique_benchmark_cases"],
              "evaluated_predictions": scoring["count"],
              "result_directory": str(results),
              "warning": "String metrics are diagnostics only; source-based accuracy requires adjudication."}
    out = results / "run_provenance.json"
    if out.exists():
        raise FileExistsError(f"REFUSE_TO_OVERWRITE: {out}")
    out.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Owner-released ChronoReg five-stage LoRA")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, default=Path("src/lora/runs/prepared"))
    parser.add_argument("--checkpoints", type=Path, default=Path("src/lora/runs/checkpoints"))
    parser.add_argument("--results", type=Path, default=Path("src/lora/runs/experiment-results-v1"))
    parser.add_argument("--execute", action="store_true", help="Requires valid reviewed release and writes adapters")
    parser.add_argument("--resume", action="store_true", help="Reuse only complete SHA-verified checkpoint prefix")
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    resolve = lambda p: p if p.is_absolute() else root / p
    cfg = load_config(root / "configs/lora.yaml")
    try:
        if args.execute:
            result = execute(root, cfg, resolve(args.release), resolve(args.prepared),
                             resolve(args.checkpoints), resolve(args.results), resume=args.resume)
        else:
            result = preflight(root, cfg, resolve(args.release), resolve(args.prepared), resolve(args.checkpoints))
    except (FileNotFoundError, OSError, ValueError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "training_started": False if not args.execute else "UNKNOWN_IF_RESUMING"},
                         ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
