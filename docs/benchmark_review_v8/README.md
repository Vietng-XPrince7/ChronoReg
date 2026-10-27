# ChronoReg benchmark temporal-causality review V8

This is a **review-only candidate** built on top of the installed V7 candidate. The canonical benchmark and LoRA trainer are not modified.

## Finding

The continual-learning evaluator currently uses `as_of_year <= checkpoint_year` as its eligibility test. Six superseded tuition questions cite the **2026 tuition decision** but were tagged 2024/2025. This could cause a model trained only through 2025 to be evaluated against knowledge from 2026.

## Proposed solution

For the six retrospective comparison questions (`BENCH_SUP_001`, `_002`, `_003`, `_004`, `_011`, `_021`), set candidate `as_of_year` and `target_year` to 2026 and record their original historical rule year in `retrospective_subject_year`. Preface each question with `Nhìn lại từ năm 2026, ...`. Keep the primary historical source and gold values unchanged. Two of these IDs are newly touched relative to V7.

Also add the missing official 2024 tuition document as a secondary source for `BENCH_SUP_012`. Carry forward the ten V7 proposed changes; the new candidate differs from the original on **12 IDs total**. All 90 rows and 37/27/26 category splits are retained.

## Critical research contract

This recommendation assumes `as_of_year` means the earliest academic-year checkpoint at which the system may answer the question, **not the historical subject year**. Team owners must explicitly agree on this semantics before promoting V8 into canonical benchmark or evaluating models. If `as_of_year` is instead used for historical selection, the evaluation API must be redesigned to pass *both* the historical subject year and a knowledge cutoff; do not silently promote V8.

The staging scripts are additive, and the gate deliberately returns code 2 `REVIEW_REQUIRED`; code 3 is an audit error. Keep the benchmark held out from model training and RAG generation prompts.
