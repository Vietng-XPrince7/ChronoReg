# ChronoReg — 7B continual QLoRA course experiment (2026-11-26)

**Status:** five stages trained and evaluated; both GGUFs exported and download hashes verified by the owner. Course snapshot only, not canonical data release, not independently frozen benchmark, not a production-quality policy assistant. This directory is additive; no raw corpus, RAG, benchmark, UI or existing 3B runner changes.

## Reproduction
- Source snapshot: `f4c228bd06662d012b397a370cdd3b2293c54744` (not the current main corpus). 80 source paths, 1,774 training and 197 validation QA, 117 held candidates. Dataset and evidence are frozen under `training/chronoreg_course/dataset/`; original source-path mapping in audit. Do not substitute later raw documents silently.
- Exact recovered FP32 runner and bundle manifest in `training/chronoreg_course/`. Manifest SHA-256 `39d5e16f266ea05a1cdc0de96d96880af6e0ea1920b1e2202d415066209c6191` matches the successful Kaggle run. Scoped `.gitattributes` prevents line-ending conversion. Original bundle README describes the initial FP16 attempt; the authoritative config is the recovered manifest and run provenance.
- Qwen2.5-7B-Instruct, NF4 double quantized base, FP32 compute, AdamW, rank 8 / alpha 16, 2 epochs per year, sequential no replay from fresh base. Single T4 14.56 GiB, torch 2.11.0+cu130, transformers 4.51.3, peft 0.15.2, accelerate 1.6.0, bitsandbytes 0.49.0, safetensors 0.8.0. Initial FP16 smoke produced NaN; FP32 smoke passed. Full training subsequently completed.
- CPU-only check from this directory: `python training/chronoreg_course/run_course_qlora.py preflight`. For Kaggle, ZIP the `chronoreg_course` folder (archive filename `ChronoReg_Kaggle_7B_FP32.zip`), upload privately, add input and import `training/ChronoReg_7B_FP32_Kaggle.ipynb`. This notebook is reconstructed from original plus successful patch, not separately rerun. Run real GPU smoke before training. Preserve the separate 3B baseline. See `export/README.md` for GGUF reproduction.

## Outcomes
| Year | Train | Validation | Train loss | Same-year validation loss |
|---|---:|---:|---:|---:|
| 2022 | 553 | 65 | 0.33303 | 0.39096 |
| 2023 | 145 | 19 | 0.35547 | 0.11066 |
| 2024 | 97 | 12 | 0.64353 | 0.52220 |
| 2025 | 694 | 72 | 0.08125 | 0.07007 |
| 2026 | 285 | 29 | 0.13720 | 0.22522 |

See exact metrics in `training/checkpoint_metadata` and `evaluation/summary.json`. 610 validation predictions across stages; 197 at the final stage, exact match 51.78%, token F1 82.97%. Lexical metrics are not factual correctness/version accuracy. E.g. incorrect tuition/scholarship amounts and admission scores remain possible; low loss does not establish policy accuracy. 2022 validation loss increases to 0.50210 in final stage. Do not claim independent comparative superiority or deploy as official advice. 1,302 rows use cohort-year proxy, 378 annual-label proxy; 281 share benchmark sources, 150 have amount overlap. Benchmark freeze and semantic evaluation remain separate team work. Curriculum dominates the train set. No claim of verified temporal availability across all documents.

## Handoff
External files (not committed): `ChronoReg_7B_Complete.zip` (all adapters/tokenizers), `qwen2.5-7b-instruct-q4_k_m.gguf`, `chronoreg-lora-7b-q4_k_m.gguf`. Owner must share via team storage; URLs not supplied. `manifests/verification.json` records the checkpoint archive hash and validation cross-check; `manifests/gguf_manifest_reported.json` records the reported, locally matched GGUF hashes. No inference test of GGUF here. The team should import these using its Ollama integration with correct year-conditioned prompt, run shared benchmark and factual review. Keep deployment model clearly distinguished from historical adapter checkpoints.
