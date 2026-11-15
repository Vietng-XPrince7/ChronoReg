# ChronoReg: Canonical Qwen2.5-3B QLoRA experiment

This is the only active LoRA model pipeline. The shared benchmark, independent
source review, RAG code and frontend are unchanged. This document does not
claim that 3B weights were trained or that QA quality has been validated.

## Model and runtime

- Base: `Qwen/Qwen2.5-3B-Instruct`, pinned to Hugging Face revision
  `aa8e72537993ba99e69dfaafa59ed015b17504d1`.
- Confirm the model's license before any commercial or public deployment.
- Quantization: NF4 4-bit with double quantization and FP16 compute.
- Minimum GPU gate: 12 GiB VRAM, preferably 16 GiB for the first test.
  This is a gate, not a promise of fitting all hardware.
- Sequential stages: 2022, 2023, 2024, 2025, 2026.
- Canonical config: `configs/lora.yaml`; one configuration, one final run.

## Training blockers

- The existing 200 template QA items are not approved source-grounded data.
- Curriculum QA drafts (including 51 + 72 candidates) still require independent review.
- Benchmark review and semantic leakage adjudication must be completed.
- No runner command may create approvals or overwrite immutable checkpoints.

### Release prerequisites

1. A curated JSONL of at least 200 **independently reviewed** QA, with at least
   30 items per start year. *Target* 300–500 if there are enough genuine
   grounded facts; do not inflate with paraphrases or fabricate sources.
2. Each training row has genuine `review_status: approved`, `id`, `question`,
   `answer`, `doc_id`, `as_of_year`, `source_file`, `source_sha256` and
   verbatim `evidence_quote`. Check cohort vs academic year and effectivity.
3. A separate frozen benchmark of 90 rows, with independent, question-by-
   question validation, and existing 42 correction and 59 overlap decisions
   reviewed. Remove exact **and semantic** overlap from train. `validate_training`
   checks exact overlap; the human ledger records semantic review.
4. An owner-issued (not AI-generated) release dossier inside the repo.
   No script creates or fabricates attestations. Changes to source bytes,
   question, answer, ledgers, prepared data, or benchmark invalidate the release.
5. Approval to run costly GPU training, and a suitable runtime.

## New training-release dossier (`chronoreg-qlora3b-release/v1`)

Place manually approved JSON under e.g. `docs/lora_releases/qlora3b_release.json`.
It must include all fields below, with **real** review evidence and SHA-256:

```
schema: chronoreg-qlora3b-release/v1
status: owner_released
independent_training_review: true
independent_benchmark_review: true
semantic_leakage_reviewed: true
owner_attestation: {reviewer, reviewed_at, decision_note}
curated_train_file, curated_train_sha256
benchmark_file, benchmark_sha256
qa_review_ledger, qa_review_sha256
benchmark_evidence_ledger, benchmark_evidence_sha256
leakage_disposition_ledger, leakage_disposition_sha256
overlap_inventory_file, overlap_inventory_sha256
full_benchmark_review_ledger, full_benchmark_review_sha256
benchmark_freeze_manifest, benchmark_freeze_manifest_sha256
prepared_manifest_sha256
```

Benchmark review and freeze manifest reuse the existing
`require_full_benchmark_review` validator. The QA review CSV must contain
exactly one row per approved QA with columns:
`candidate_id,decision,source_verified,cohort_effectivity_verified,semantic_leakage_cleared,independent_reviewer_signoff,reviewer,reviewed_at,reviewer_note,question_sha256,answer_sha256,source_sha256`.
All `*_verified`, `*_cleared` and `*_signoff` values must be `YES`.
`question_sha256` and `answer_sha256` are SHA-256 of each exact UTF-8 text.
Legacy correction ledger requires exactly 42 accepted items; legacy overlap
ledger and inventory must contain the same 59 adjudicated pairs. The 2024-026
quarantine must remain. None of these files are created by the runner.

This validator checks artifact consistency, not human identity or the truth of
individual answers. The team must independently assess content and governance.

## Commands (from ChronoReg repo root on a suitable Linux CUDA machine)

Install runtime dependencies in a **new virtual environment**, in a clean environment. Pin tested package versions after first validation and document them:

```bash
python -m venv .venv-qlora3b
source .venv-qlora3b/bin/activate
python -m pip install --upgrade pip
# Install compatible NVIDIA PyTorch from pytorch.org for the machine's CUDA.
python -m pip install 'transformers>=4.46.3,<5' 'peft>=0.13.2,<1' \
  'accelerate>=1.1.1,<2' 'bitsandbytes>=0.45,<1' 'PyYAML>=6' 'safetensors>=0.4.5'
python -m unittest discover -s tests -p test_qlora3b.py -v
```

The `stage` command validates existing human-approved source-linked QA,
requires 200 items and 90 distinct held-out benchmark rows. It writes a new,
non-reusable staging directory but **never releases it**:

```bash
python -m src.lora.qlora3b --repo . \
  stage --train src/lora/runs/qlora3b/curated_approved_qa.jsonl
```

Read-only release check, still **no GPU load**:

```bash
python -m src.lora.qlora3b --repo . \
  --release docs/lora_releases/qlora3b_release.json preflight
```

If it prints `BLOCKED`, stop. Do not fake approval records.
Only with real release + suitable GPU + explicit owner budget authorization:

```bash
python -m src.lora.qlora3b --repo . \
  --release docs/lora_releases/qlora3b_release.json train
# If interrupted after a stage checkpoint (never after a partial file):
python -m src.lora.qlora3b --repo . \
  --release docs/lora_releases/qlora3b_release.json train --resume
python -m src.lora.qlora3b --repo . \
  --release docs/lora_releases/qlora3b_release.json \
  evaluate --output src/lora/runs/qlora3b/evaluation-v1
```

**Stop gate**: One run, 5 verified 3B checkpoints, full held-out
`predictions.jsonl`, `forgetting_summary.json`, `qlora3b_provenance.json`,
manual version/outdated analysis by the evaluation owner, reproducibility notes,
no benchmark contamination. Document failure/weak quality rather than
retraining on the held-out answers. Do not claim version accuracy or factual quality without source verification.
