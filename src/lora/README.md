# ChronoReg | Continual QLoRA 3B

**Active LoRA model:** `Qwen/Qwen2.5-3B-Instruct` (NF4 4-bit, FP16 compute).
**Canonical config:** `configs/lora.yaml`. This is the ONLY active LoRA training profile.
**Canonical entrypoint:** `python -m src.lora.cli` (delegates to QLoRA 3B).

## State

- The QLoRA 3B source code is installed, but NO real 3B adapter checkpoints have been trained.
- All source-backed training QA and the independent held-out benchmark must be reviewed before live training.
- The release gate requires >=200 independently approved QA with >=30 per year, 90 benchmark questions, and genuine review ledgers.
- CUDA on an NVIDIA GPU with >=12 GiB VRAM is required by the runner (16 GiB preferred). This is not a memory guarantee.
- Current datasets are drafts; the release guard must NOT be bypassed.
- A model-only answer has `sources=[]` and cannot make document-backed claims.

## Commands

```bash
python -m unittest discover -s tests -p 'test_qlora3b.py' -v
python -m src.lora.cli --help
python -m src.lora.cli --repo . preflight --help
# The following is intentionally BLOCKED until real independent approvals exist:
python -m src.lora.cli --repo . --release docs/lora_releases/qlora3b_release.json preflight
```

For `stage`, `train`, `evaluate` and `answer` options, use `python -m src.lora.cli --help`.
QA candidate/review actions are available via `python -m src.lora.review_cli --help`.

See `docs/qlora3b_experiment.md` for the release schema, real training procedure, licensing, and the fixed stop gate.
**Do not** confuse passing offline tests with model convergence, knowledge quality or a valid trained checkpoint.
