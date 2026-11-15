# ChronoReg | Continual QLoRA 3B (course experiment, 15 Nov 2026)

This directory contains the **actual results of a 5-stage sequential QLoRA experiment** on Qwen2.5-3B-Instruct, run on Kaggle T4 for the UET policy QA course project. This is a course-mode experiment, **NOT** a human-reviewed official policy-data release. It does **not** replace the separately gated official training/release pipeline in `src/lora/`.

## For Việt: after this PR is merged into `main`

```powershell
git pull origin main
python experiments/qlora3b_course_20261115/verify_assets.py
```

The first command downloads the complete experiment including **5 trained adapter weight files**. The second command verifies hash chain, row counts, and 450 benchmark predictions. **No new training required**.

## Directory

- `checkpoints/year-2022` through `checkpoints/year-2026`: adapter weights, PEFT config, tokenizer, stage metadata.
- `checkpoints/course_run_provenance.json`, `checkpoints/five_stage_completion.json`: original GPU training record.
- `training/course_train_200.jsonl`: 200 course-mode QA pairs (40/37/36/49/38 by proposed year).
- `training/manifest.json` and `training/OFFLINE_AUDIT.json`: training-data provenance and machine checks.
- `reproduction/course_train_runner.py`, Kaggle notebook, tests: reproduction code.
- `evaluation/predictions.jsonl`: 450 responses (90 benchmark questions x 5 adapters).
- `evaluation/forgetting_summary.json`, `evaluation/provenance.json`: evaluation summaries and provenance.
- `analysis/`: breakdown tables, diagnostic predictions, and Vietnamese report.
- `inference_example.py`: sample base-model + adapter inference; requires separate Qwen2.5-3B-Instruct weights and CUDA.
- `COURSE_MANIFEST.json`: file-level SHA256 manifest for this experiment.

## Experiment facts

| Stage | Train QA | Epochs | Mean Token F1 proxy (90 fixed benchmark items) |
|---|---:|---:|---:|
| 2022 | 40 | 2 | 0.4616 |
| 2023 | 37 | 2 | 0.4430 |
| 2024 | 36 | 2 | 0.4042 |
| 2025 | 49 | 2 | 0.3613 |
| 2026 | 38 | 2 | 0.3723 |

The 5 adapter files were trained **sequentially** (each year continued the previous adapter), not as 5 isolated baselines. The fall in lexical F1 is not itself proof of catastrophic forgetting: the fixed 90-question benchmark includes future policy questions relative to early checkpoints.

**Important:** The year labels in training are proposed and were not independently reviewed for full legal effectivity. Machine-checked excerpt consistency does not certify that policy amounts/year rules are correct. Token F1 is not factual accuracy, version accuracy, or outdated-answer rate.

## Quick inference on Kaggle / NVIDIA CUDA

Use the same base model family **Qwen2.5-3B-Instruct, Transformers format**. The 3B base model itself is not in this repo.

```bash
python experiments/qlora3b_course_20261115/inference_example.py \
  --base-model /path/to/Qwen2.5-3B-Instruct \
  --adapter experiments/qlora3b_course_20261115/checkpoints/year-2026 \
  --year 2026 --question 'Học phí năm học 2026-2027 là bao nhiêu?'
```

Base model is explicitly loaded separately; `adapter_config.json` may contain the old Kaggle model-folder reference. Do not rely on that reference on Việt's machine. Do not present generated answers as verified UET policy without source-checking.

## Comparison caveat

The repository's existing `runs/eval` RAG baselines currently return excerpts from BM25 retrieval, while this LoRA experiment generates 3B model answers. They use the same benchmark question IDs but have different answer-production protocols. Compare lexical scores descriptively and **do not claim a controlled RAG-vs-LoRA superiority result** without normalizing evaluation protocol and assessing semantic correctness.

See `analysis/ChronoReg_QLoRA3B_Evaluation_Report_VI.md` for detailed plots, errors, and limitations.
