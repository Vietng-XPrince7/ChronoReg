# Unified QA review packet

This module creates one *read-only* review worklist from prose and table QA drafts. It does not approve QA, edit the human decision records, or create training data. All candidates are revalidated against verified source metadata, source SHA-256, excerpt text, academic year, and publication holds before the report is written.

## Run on an existing ChronoReg-LoRA worktree

From `C:\HaiAnh\ChronoReg-LoRA` in PowerShell:

```powershell
py -m src.versioning.cli build

# Keep the original 119-row candidate/review set untouched.
py -m src.lora.table_candidates `
    --output src/lora/runs/table_candidates_v2.jsonl

py -m src.lora.review_packet
```

Outputs are created under `src/lora/runs/`:

- `review_packet_v2.csv`: a UTF-8 BOM CSV, safe for spreadsheet opening, listing provenance, evidence, current question/answer drafts, risk flags, and review priority.
- `review_packet_v2_manifest.json`: SHA-256 digests for all input files and per-year counts. The manifest explicitly records that **zero rows are approved** and that benchmark isolation is **not certified**.

Neither file is a dataset for training. The CSV is a *review aid only*: changing a CSV cell does not constitute approval or update any signed decision JSONL.

To generate a **new review template** for the regenerated table drafts, use separate output paths:

```powershell
py -m src.lora.cli review-template `
    --candidates src/lora/runs/table_candidates_v2.jsonl `
    --output src/lora/runs/table_review_decisions_v2.jsonl `
    --coverage src/lora/runs/table_review_coverage_v2.csv
```

These commands refuse to overwrite an existing packet or candidates. If any of the above output paths already exist, inspect them instead of deleting or overwriting them. Do not reuse decisions from the earlier 119 candidates, because the candidate identities and counts may differ.

## Review process

Review the high-priority flags first, then independently verify each remaining answer against the original UET PDF and applicable amendments. Edit the corresponding `review_decisions*.jsonl`, not the CSV, providing a reviewer, review date, substantive note, and rewritten question. Run `review-finalize` for the **matching** candidate and decision file. A benchmark from the data/evaluation owner must be checked separately before preparing official training data.

Priority labels indicate work order, **not correctness**:

- `P0`: possible identifier-as-answer, duplicate question, or benchmark overlap. Keep on hold and rewrite or reject.
- `P1`: ambiguous section context or generic paragraph question. Rewrite and recheck the source.
- `P2`: no static defect detected, but still requires original PDF, effective-scope and amendment verification.

`OFFICIAL_SOURCE_REVIEW_REQUIRED` appears on every row. Even with an optional frozen benchmark supplied via `--benchmark`, lexical overlap checks cannot prove absence of semantic leakage.

The start year of the academic year is represented by `as_of_year`. Confirm this convention with the benchmark owner before official comparisons.

### Validation

```powershell
py -m pytest -q `
    tests/test_lora_pipeline.py `
    tests/test_lora_gpu_config.py `
    tests/test_lora_qa_review.py `
    tests/test_lora_table_candidates.py `
    tests/test_lora_table_audit.py `
    tests/test_lora_review_packet.py
```

No Torch, model download, GPU, or edits to `src/rag/`, `src/ingestion/`, `src/eval/`, `data/`, `docs/schema.md`, or shared `models.py` are needed.
