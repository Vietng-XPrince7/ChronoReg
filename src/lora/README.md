# ChronoReg: Continual LoRA

This module belongs to `feature/lora-continual`. It does not change `src/ingestion/`, `src/eval/`, `src/rag/`, `src/versioning/`, `src/ingestion/models.py`, `docs/schema.md`, or the shared dependency file.

## Current status

- Implemented and unit-tested offline: candidate generation from verified Markdown, approved QA validation, source hash verification, benchmark-leakage guards, chronological dataset preparation, a sequential PEFT training backend, inference contract, and a held-out forgetting diagnostic.
- **Not** trained on real UET QA yet. Validated year-specific QA and held-out benchmark from the data/eval owner are required. No claims about accuracy or forgetting are possible before real training.
- Verified document metadata is not a substitute for question/answer human review. Generated candidate QAs remain `draft` and cannot be trained without explicit approval.

## Team contracts to agree before any reported result

- `as_of_year: int` here means the **starting year of the academic year** (`2025` = 2025–2026). This is a provisional assumption requiring sign-off from the data/eval owner. It is **not** a calendar-effective-date.
- Shared answer callable: `LoRAAnswerer(config, adapter).answer(question: str, as_of_year: int | None) -> dict`, returning `answer` and `sources` plus audit fields. `sources=[]` is intentional: LoRA does not retrieve evidence and must not invent citations. The team `src/eval/` scores version accuracy and semantic outdated answers.
- Held-out benchmark expected keys: `id`, `question`, `type`, `as_of_year`, `gold_answer`, `gold_doc_id`, and optionally `outdated_answer`. The benchmark must be held out from training and model selection. `gold_doc_id` must match the data/versioning `doc_id` namespace.
- Source/QAs must not include private student names, IDs, or other personal data.

## Installation (Windows / PowerShell)

Install Python package dependencies in an isolated venv. The training stack should be installed **only after** PyTorch and the GPU have been checked. Run all commands from the ChronoReg repository root:

```powershell
py -m venv .venv-lora
.\.venv-lora\Scripts\python.exe -m pip install --upgrade pip
.\.venv-lora\Scripts\python.exe -m pip install -r src/lora/requirements.txt
.\.venv-lora\Scripts\python.exe -m pytest -q tests/test_lora_pipeline.py
```

`torch` is *not* installed by this requirements file; first inspect `nvidia-smi`, and use the correct PyTorch build from https://pytorch.org/get-started/locally/. If the GPU or Python 3.13 environment cannot support the selected package combination, use a compatible dedicated Python environment or a free Colab GPU; keep the source branch unchanged. Do not install `bitsandbytes` blindly on Windows. A 0.5B baseline is chosen to minimize resource requirements, not because it is proven best. The full repository's `requirements.txt` contains older shared pins; coordinate upgrades with the group instead of changing it here.

To run only the data unit tests you need `pytest` and `PyYAML`; these tests do not download or load any LLM.

## Step 1: Draft question/answer candidates from verified sources

After the data owner provides `data/versioning/documents.jsonl` (created by `py -m src.versioning.cli build` when the versioning module is available):

```powershell
py -m src.lora.cli propose
```

Candidates are saved to `src/lora/runs/candidates.jsonl` and explicitly marked `review_status: "draft"`. They consist of exact source excerpts and provenance, **not verified training examples**. Many documents are tables/schedules, which require carefully authored fact-level questions; the generator deliberately skips complex tables.

For each candidate, a reviewer must check the correct year, target population, applicable program, year-specific change, legal scope, and exact evidence. Rewrite weak questions; do not manually replace a value without also updating/rechecking its source evidence and SHA. Store approved QAs in `src/lora/runs/approved_qa.jsonl` with:

```json
{
  "id": "unique-reviewed-qa-id",
  "question": "<a reviewer-authored question about a specific year>",
  "answer": "<a source-verified answer>",
  "doc_id": "<an existing, reviewed ChronoReg document ID>",
  "as_of_year": 2025,
  "academic_year": "2025-2026",
  "evidence_quote": "<an exact passage from the original Markdown>",
  "source_file": "data/raw/uet/markdown/2025/<file>.md",
  "source_sha256": "<SHA256 of that Markdown file>",
  "review_status": "approved"
}
```

This is a **schema illustration**, not a real UET fact and not a complete runnable example. Do not commit private/unreviewed QA. The script verifies the file exists, SHA-256 matches, and the quotation is verbatim. It does not independently prove the answer's legal correctness; reviewers remain responsible.

## Step 2: Stage year-specific QA without benchmark overlap

Once the benchmark owner supplies their final held-out file, update `configs/lora.yaml` paths and agreed `as_of_year` convention. Run:

```powershell
py -m src.lora.cli prepare
```

The script refuses invalid years, duplicated question IDs, overlapping benchmark questions, missing citations/hashes, missing year data, or unapproved QAs. Outputs `train_2022.jsonl`, ..., `train_2026.jsonl` and `manifest.json` inside the locally ignored `src/lora/runs/prepared/`. The benchmark is not used as the training validation set.

**Important:** The protected benchmark should remain unseen during training decisions. For model tuning, request a separate development split from the data owner. Repeatable benchmark checks after training stages are for final reporting and could induce selection bias if used iteratively.

## Step 3: Train sequential adapters

Edit and pin `base_model` and `model_revision` in `configs/lora.yaml` before a final run. Verify model license, hardware, memory capacity, and tokenizer compatibility. The default baseline is `Qwen/Qwen2.5-0.5B-Instruct` (Apache 2.0 license on its model card).

Start with an offline plan (no Torch, GPU, or download):

```powershell
py -m src.lora.cli train --year 2022 --dry-run
```

Then train only if approved data and a compatible GPU are available:

```powershell
py -m src.lora.cli train --year 2022
py -m src.lora.cli train --year 2023 --previous src/lora/runs/checkpoints/year-2022
py -m src.lora.cli train --year 2024 --previous src/lora/runs/checkpoints/year-2023
py -m src.lora.cli train --year 2025 --previous src/lora/runs/checkpoints/year-2024
py -m src.lora.cli train --year 2026 --previous src/lora/runs/checkpoints/year-2025
```

Every stage reads **only that year's** approved QA and resumes the **same trainable adapter** from the prior year. Its local `stage.json` records previous checkpoint, base model, revision, year, and QA fingerprint. The stage refuses an overwritten or missing checkpoint, nonconsecutive years, a different model, or a changed prepared training file. Checkpoint files remain untracked in `src/lora/runs/`.

`--allow-cpu` exists only for tiny smoke tests; multi-epoch continual training on CPU is not recommended. The Qwen baseline now loads with an explicit FP16 dtype on CUDA (and FP32 for CPU smoke tests), uses eager attention and optional non-reentrant gradient checkpointing. This is ordinary LoRA, **not** QLoRA. The GPU smoke reached 1,151 MiB allocated / 1,252 MiB reserved at 105 tokens; this does not prove 512-token full Trainer fits 4 GB.

## Step 4: Interface and forgetting diagnostics

```powershell
py -m src.lora.cli answer --adapter src/lora/runs/checkpoints/year-2025 --as-of-year 2023 --question "<a real evaluation question>"
py -m src.lora.cli evaluate
```

`answer` returns `answer`, `sources` (empty: no evidence retrieval), and `as_of_year`. Asking without a year returns a request for year clarification rather than guessing the current year. A LoRA model may still hallucinate despite the system prompt.

`evaluate` loads each checkpoint **one at a time**, tests all *already introduced* years, stores predictions and per-year exact-match changes. Diagnostics include normalized exact-match, token F1, and an explicit-string outdated-answer **proxy only**. They are not substitutes for version accuracy, groundedness, or semantic outdated-answer rate defined by the evaluation branch.

Forgetting at checkpoint `t` for an earlier year `y` is measured as `max(0, max_{s in [y, t)} score(s,y) - score(t,y))`. Future-year benchmark questions are never evaluated at earlier checkpoints.

## Integration and limits

- Do not edit `src/eval/`, `src/ingestion/models.py`, or `docs/schema.md` on this branch.
- No approved QA/benchmark currently means **the pipeline is ready to integrate but not empirically trained**.
- Before publishing results, add an *independent adapter per year* baseline and a *replay* baseline if the course allows. The provided implementation is the requested sequential strategy.
- Potential source exclusions (temporary tuition notices, superseded documents, unsafe tables) must be decided by the data owner. The LoRA candidate generator only reads `policy_qa_ready` and `verified_against_source` flags.
- Confirm with the group whether a single answer can have several supporting `gold_doc_id`s and whether `as_of_year` means calendar or academic year. These are interface decisions owned by the data/eval branch, not changes to make locally.


## Quadro T1000 GPU validation (Ubuntu WSL2)

On 2026-10-23, the Windows host's Code Integrity policy blocked a PyTorch DLL.
The same Quadro T1000 GPU successfully executed FP16 CUDA under Ubuntu WSL2
with Python 3.13.17, torch 2.9.1+cu126, transformers 4.57.6, PEFT 0.21.2,
and accelerate 1.15.0. An isolated synthetic 105-token optimizer step used
1,151 MiB allocated / 1,252 MiB reserved. These numbers are **not** a training
benchmark and do not justify accuracy/forgetting claims.

The `model_dtype: float16` setting avoids automatically reloading Qwen's BF16
weights onto a Turing GPU that lacks native BF16. CUDA BF16 is rejected unless
supported. For tiny CPU smoke tests, model weights are loaded as FP32.

The default first-run maximum length has been reduced to 512 tokens, batch size 1.
Memory remains workload dependent; explicitly inspect peak allocated/reserved
memory and reduce length if needed. Stage code saves a PEFT adapter to a partial
folder and publishes only after the serialized safetensors file is verified.

Once GPU dependencies are installed and the smoke model weights are cached,
run **only the synthetic end-to-end stage test**, without touching real QA:

```bash
cd /mnt/c/HaiAnh/ChronoReg-LoRA
"$HOME/.local/share/chronoreg-lora/py313/bin/python" -m src.lora.smoke_stage
```

It creates an isolated temporary workspace, generates exactly two synthetic QAs,
executes one Trainer step each for 2025 and 2026, checks adapter artifacts and
loads the final adapter for one synthetic inference. It is NOT a full five-year
experiment; a failure must be diagnosed before using the real `train` command.
The synthetic source is not UET policy and temporary checkpoints are removed.

The course's real five-year run requires independent approved source-backed QAs,
a held-out benchmark owned by the data/eval branch, and a signed-off year
convention. Do not commit `src/lora/runs/` or publish synthetic scores as
regulatory QA accuracy.
