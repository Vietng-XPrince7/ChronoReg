# Continual LoRA: held-out forgetting diagnostics

`python -m src.lora.cli evaluate` evaluates checkpoints in chronological order. At a
checkpoint for year `t`, questions from years after `t` are **not evaluated**.
Each older year is re-tested to measure loss of previously learned capability.

The summary now includes the existing normalized exact-match matrix and
`forgetting_exact_match_drop`, plus a parallel whitespace-token-F1 score matrix,
`forgetting_token_f1_drop`, per-checkpoint sample counts, and macro-average
forgetting over historical years. The prediction log retains each model answer,
source document ID, checkpoint year, per-case exact match, and token F1.

For metric `m` and an earlier year `y` after checkpoint `t`:

```
Forgetting_m(t, y) = max(0, max(m(s, y) for y <= s < t) - m(t, y))
```

The macro mean averages forgetting over evaluated previous years; the first
checkpoint has no previous year and reports `null`. Scores are in the range
0.0 to 1.0. When a year has no benchmark cases, it is absent (not zero).

These are **string similarity diagnostics**, not evidence-based grading.
Vietnamese whitespace token F1 is not a semantic metric and may miss important
numerical/legal errors; exact match can penalize semantically correct paraphrases.
The team's `src/eval/` system remains responsible for policy version accuracy,
outdated answers, and overall benchmark scoring.

Do not evaluate on the held-out benchmark to choose hyperparameters or rewrite
training questions. The data/eval owner must freeze the repaired benchmark
before the five-year experiment. Use a separate development set for tuning.
No training data, benchmark items, adapters, or course scores are modified by
this change. Existing report keys remain available.
