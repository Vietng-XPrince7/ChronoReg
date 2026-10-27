# Temporal Evaluation Contract for ChronoReg LoRA

## Status

**Diagnostic-only and pre-freeze.** This change neither approves benchmark content nor
changes any training examples, adapters or release gates. Do not use these metrics as
final experimental results until the evaluation owners sign off on the exact benchmark
version and the semantics of `answer(question, as_of_year)`.

## The two years in retrospective questions

For an ordinary question, `as_of_year` is the applicable checkpoint/prompt year,
and the historical subject is that same year. For questions whose answer references
a decision released later than the policy year being described, the V8 review
candidate uses:

- `as_of_year`: **earliest eligible evaluation checkpoint/prompt year**. For
  example, 2026 for a question that explicitly compares a 2025–2026 fee against
  a 2026–2027 decision.
- `retrospective_subject_year`: year of the older policy being discussed. For
  example, 2025 in that same question.

These are evaluation interpretation rules for the **V8 review candidate**. Other
coursework and shared RAG data may still interpret `as_of_year` as the academic
year requested. Do not silently change the shared interface: agree on a common
versioned contract before cross-method comparisons. For finer temporal correctness,
year-only metadata cannot resolve decisions published or effective midway through
an academic year; record precise publication and effective dates separately.

## Eligibility

A benchmark item is shown only at checkpoints `stage >= as_of_year`. This
ensures a 2026 retrospective comparison is never queried at a 2025 checkpoint.
No gold answer is fed to the predictor; it is used for scoring only. Nothing here
permits training on benchmark questions or selecting model configurations by
held-out benchmark scores.

## Metric interpretation

Older output keys are retained without modification for consumers already using
them. Specifically, `held_out_token_f1_by_checkpoint` and legacy forgetting
remain grouped by `as_of_year` (first eligibility). **They are not history-year
forgetting metrics for retrospective questions.**

Additional outputs:

- `policy_subject_token_f1_by_checkpoint`: per-policy-year diagnostic F1.
- `policy_subject_count_by_checkpoint`: denominator; it may change over stages.
- `case_stable_forgetting_*_by_subject_year`: each included benchmark ID has a
  prior observation; its decrease from its own best preceding score is measured.
  New cases are not treated as forgotten when they first appear.
- `case_stable_forgetting_comparable_counts`: comparable IDs used per checkpoint
  and policy subject year. The first observation has no forgetting value.

All these are **string-level** diagnostics, not legal/semantic correctness.
Exact match or token F1 can be misleading for numeric answers and paraphrases.
A separate independent, source-anchored adjudication is needed.

## Data isolation and reproducibility

The patch only modifies `src/lora/evaluate.py` and adds this document and a
regression test. It preserves the `predict(stage, question, as_of_year)` API,
original summary keys and existing `src/lora/metrics.py` behavior. The V8
90-item candidate stays in `docs/benchmark_review_v8/review_only/`; neither
this change nor its tests freeze or replace the canonical benchmark.

Before accepting an evaluation release, record benchmark SHA-256, exact candidate
version, source-effective-date adjudication, training release manifest and
independent semantic leakage review. The current 200 legacy QA remain ineligible.
