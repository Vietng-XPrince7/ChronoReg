# Human QA review sheet

The unified packet (`review_packet_v2.csv`) is an immutable review reference. It is not an approval record. This tool exports a separate **editable** UTF-8 CSV and later converts an explicitly reviewed sheet into the existing source-bound JSONL decisions. It never approves anything on its own.

## Preparation

From `C:\HaiAnh\ChronoReg-LoRA` (PowerShell), after the earlier `review_packet_v2.csv` has been generated:

```powershell
py -m src.lora.review_sheet export
```

This creates `src/lora/runs/review_sheet_v2.csv` with 138 rows on the currently audited input. All rows initially have `decision=pending`; `reviewed_question`, `verified_answer`, `reviewer_name`, `review_date`, and `review_note` are blank.

Open the CSV in a spreadsheet program **with all columns imported as text** (Excel: Data > From Text/CSV and set each column to Text) to prevent automatic date/ID conversion. Keep the original order and headings. Do not change any of the prefilled columns. A reviewer's edits are confined to the six fields named above. Save as UTF-8 CSV. Keep a local backup before editing.

For each reviewed item, inspect the source document, the **official UET PDF**, effective academic-year scope and any amendment. For a reliable answer, `reviewed_question` must be a genuinely rewritten, concrete question and `verified_answer` must match the reviewed source. Set `decision` to exactly `approve`, `reject`, or leave `pending`. Approval or rejection also requires `reviewer_name`, ISO `review_date` (`YYYY-MM-DD`) and a substantive `review_note` (at least 12 characters). Rejections must have blank rewritten question and answer. Pending rows must have blank review fields.

A source SHA only verifies that the Markdown has not changed; it does *not* establish that the converted Markdown or its original PDF is accurate. The `priority` and `risk_flags` fields tell you what to check first, never whether a fact is correct.

## Import explicitly reviewed decisions

```powershell
py -m src.lora.review_sheet import
```

The import re-checks every candidate against its registry, original Markdown, document SHA, publication holds, candidate fingerprint, and the prefilled immutable CSV fields. It refuses missing/duplicate/altered rows, invalid review decisions, unreviewed approvals, and conflicting approved questions. It creates two **new** files, never overwriting an existing artifact:

- `src/lora/runs/combined_candidates_v2.jsonl`
- `src/lora/runs/combined_decisions_v2.jsonl`

If the official, frozen benchmark from the data/evaluation owner is already available, include `--benchmark path/to/frozen_benchmark.jsonl`. This checks direct leakage during import; it does not prove semantic independence or certify the benchmark split. Without an official benchmark, approval records remain **not ready for experimental training**.

If you need to revise an existing imported sheet, keep the prior review artifacts and choose **new `--combined` and `--decisions` output names** instead of deleting or overwriting the originals.

## Finalize (only after human review)

The combined records can enter the existing review workflow:

```powershell
py -m src.lora.cli review-finalize `
  --candidates src/lora/runs/combined_candidates_v2.jsonl `
  --decisions src/lora/runs/combined_decisions_v2.jsonl `
  --output src/lora/runs/approved_combined_v2.jsonl `
  --coverage src/lora/runs/approved_combined_coverage_v2.csv
```

Use `--benchmark` with the frozen official benchmark if supplied, then run the existing `prepare` gate with the benchmark. The tool has no ability to verify a person's identity or confirm the truth of a handwritten review: those remain human responsibilities.

Do not add source Markdown, drafts, approved QA files, reviewer names, or checkpoint artifacts to Git without your team's explicit agreement. This feature only adds code/tests/documentation under `src/lora/` and `tests/`.

## Tests

```powershell
py -m pytest -q `
  tests/test_lora_pipeline.py `
  tests/test_lora_gpu_config.py `
  tests/test_lora_qa_review.py `
  tests/test_lora_table_candidates.py `
  tests/test_lora_table_audit.py `
  tests/test_lora_review_packet.py `
  tests/test_lora_review_sheet.py
```
