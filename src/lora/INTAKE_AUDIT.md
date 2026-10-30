# LoRA data intake audit

The handoff snapshot received on 2026-10-27 contains 90 evaluation questions and
200 training questions. Do not run real continual fine-tuning on the snapshot as-is.

Run from the repository root:

```powershell
py -m src.lora.intake_audit `
  --report src/lora/runs/intake_audit_20261027.json `
  --cases src/lora/runs/intake_cases_20261027.jsonl
```

This command audits inputs without changing them; it prints `BLOCKED_FOR_TRAINING`
when any hard blockers are found. To use the status as an exit-code gate, add
`--require-ready`. Outputs cannot overwrite earlier audits.

Findings on the provided snapshot:

- All 200 training rows claim review by `Antigravity QA Reviewer` and contain a
  shared non-answer template. Source SHA-256 and verbatim evidence checks pass;
  neither check proves the answer is responsive or that a person reviewed it.
- 105 training questions match generic question patterns. These are diagnostic
  flags only; automatically detected templates or non-human approval claims are
  blockers in `prepare`.
- The training source hash, benchmark hash and all five stage-file hashes disagree
  with the committed prepared manifest. This cannot be treated as a reproducible
  experiment. Rebuild from genuinely reviewed QA, never rewrite hashes to hide
  the issue.
- The benchmark has 37 active-rule, 27 superseded-rule and 26 year-specific
  questions; all 90 source hashes resolve to Markdown documents in the snapshot.
  The 22 benchmark document IDs also appear in the train source inventory.
  Document overlap is expected in many QA tasks but facts and paraphrases must
  still be checked for train/test contamination.
- The benchmark's alternate JSON export agrees on common fields and IDs. Its
  richer JSONL version includes the evaluation interface aliases.

## Recovery path

1. Retain `data/qa_benchmark/benchmark.jsonl` as held out. Do not copy its
   answers, `key_facts`, or paraphrases into training QA.
2. Review existing source-backed draft candidates using the LoRA review tools.
   Each approval requires a fact-specific question, a responsive answer, correct
   year/unit/program scope, a verbatim source quote and a *real* reviewer.
3. Resolve dubious scope and contradictory university notices before approval.
4. Check semantic leakage against the benchmark with human review. The code can
   detect exact duplicates and hash issues but cannot certify paraphrase or
   factual overlap.
5. Export the independently approved rows to a **new** path, then run `prepare`
   to generate new year partitions and a new manifest. Do not overwrite or
   rename the 200 placeholder rows as curated data.
6. Only after that, train sequential checkpoints in chronological order and
   evaluate each stage on *previously introduced years*. Record a non-continual
   baseline when reporting forgetting.

This patch changes only `src/lora/prepare.py` and adds an audit module and tests.
It does not modify source data, shared schemas, RAG, evaluation gold labels or
existing checkpoints. Existing synthetic smoke runs remain outside the real-data
approval requirement. The audit is not semantic fact-checking.
