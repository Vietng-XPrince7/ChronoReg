# LoRA five-stage execution contract

## Purpose

One controlled command trains 2022, 2023, 2024, 2025, 2026 **sequentially** and then evaluates all complete checkpoints against a frozen held-out benchmark. This does not create independent review attestations, freeze the benchmark, or permit training on unreviewed data.

This implementation deliberately leaves `src/lora/release_guard.py`, `configs/lora.yaml`, all source documents, the canonical benchmark, and training data unchanged.

## Before execution

1. The model revision must be a verified full-length Hugging Face commit SHA rather than `main`. Pin it in `configs/lora.yaml` in a separate reviewed commit before preparing final experiment artifacts. The Qwen model has already been downloaded locally for synthetic smoke; a pinned revision must still be confirmed.
2. `--prepared` must refer to the *independently approved* chronological QA set and contain all five `train_YYYY.jsonl` with matching hashes.
3. `--release` must point inside the repository to an authentic owner-approved release dossier. The existing guard requires 90 independently reviewed benchmark cases, 42 accepted correction decisions, 59 independently adjudicated leakage pairs, an approved freeze manifest, and 24 specific V3 curated examples. **The 37 example preview cannot be used until a separately reviewed release schema explicitly supports it.**
4. Use a new `--results` output path. Never erase or overwrite adapters produced by a previous experiment.
5. Always keep held-out answers and questions out of training selection. The scorer is diagnostic; report semantic rule accuracy separately.

## Read-only preflight

From repository root after review, pinning, and release:

```powershell
$py = 'C:\HaiAnh\ChronoReg-LoRA-GPU-Venv\Scripts\python.exe'
& $py -m src.lora.run_five_stages --repo . --release docs/lora_releases/owner_release.json
```

If any condition fails, the command prints `BLOCKED` and exits code 2 without loading model weights.

## Execute / recover

Only after preflight explicitly returns `READY_FOR_RELEASED_EXECUTION`:

```powershell
& $py -m src.lora.run_five_stages --repo . --release docs/lora_releases/owner_release.json --execute
```

If an interrupted run already has complete verified adapters, specify `--resume`, and choose a **new** results path if an incomplete evaluation directory exists:

```powershell
& $py -m src.lora.run_five_stages --repo . --release docs/lora_releases/owner_release.json --execute --resume --results src/lora/runs/experiment-results-recovery-v1
```

The runner compares existing checkpoints with the current release digest, model pin and exact year dataset SHA. It never reuses a checkpoint with mismatched provenance. It evaluates all five stages and writes `predictions.jsonl`, `forgetting_summary.json`, `run_provenance.json` only after the staged chain completes.

## Current status (October 27, 2026)

CUDA/FP32 production-shape synthetic stress passed on an NVIDIA Quadro T1000 4 GiB. Actual UET five-stage training has **not** run. The canonical QA set in the repository still points at 200 legacy template items; the V3 24-item set and Batch A 37-item review preview have not received independent final signoff. The benchmark 90-case owner ledger remains pending. Consequently execution **must remain blocked** until these specific decisions are made. This testable orchestration alone is not an experimental result.
