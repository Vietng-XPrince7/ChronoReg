# Table QA quality triage

The table extractor generates draft candidates, not ground truth. `table_audit`
validates that each candidate still matches its verified Markdown source and
creates a **read-only, non-overwriting** review worklist. It does not approve,
reject, train on, or modify QA records.

From the repository root, after `src.lora.table_candidates` has generated
`src/lora/runs/table_candidates.jsonl`:

```powershell
py -m src.lora.table_audit
```

The worklist is written to `src/lora/runs/table_quality_audit.csv`. It carries
candidate fingerprints, exact evidence rows, sections, row and column labels,
and potential quality risks. Open it in Excel and filter `review_action` to
`HOLD_FOR_REWRITE` first. Do not treat any row marked
`CHECK_ORIGINAL_PDF_AND_AMENDMENTS` as approved: **all** rows require source
verification and editorial review. Review the original UET decision, table
footnotes, cohort scope, units, effective period and amendments before editing
`table_review_decisions.jsonl` manually.

`IDENTIFIER_COLUMN` / `NON_MONETARY_VALUE` flag legacy drafts whose answers
are table codes (for example `I.1` or `ThS.1`). `GENERIC_SECTION` flags drafts
whose heading is only the decision preamble and may omit essential context.
The extractor now excludes identifier columns and requires numeric values, but
already generated candidates/review decisions are preserved unchanged.

The audit may optionally read the team's frozen held-out benchmark:

```powershell
py -m src.lora.table_audit --benchmark data/qa_benchmark/benchmark.jsonl \
  --output src/lora/runs/table_quality_audit_with_benchmark.csv
```

Use the actual file path provided by the data/eval owner. This optional check
flags identical questions and highly similar questions for the same document;
it **cannot certify semantic non-overlap** or replace the group's evaluation
protocol. Never train on the benchmark. Do not overwrite an existing audit
output. To rerun, specify a new `--output` filename, not the human review file.

The audit does not modify any files in `src/rag/`, `src/ingestion/`, `src/eval/`
or the team's shared schema. It creates no approved QA or model checkpoint.
