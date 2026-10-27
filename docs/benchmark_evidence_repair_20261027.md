# Benchmark evidence repair (2026-10-27)

This is a source-grounded proposed correction set for the benchmark delivered in commit `ec49bf8`. It requires acceptance by the benchmark data owner before becoming the frozen evaluation version.

## Scope and outcome

- 90 benchmark IDs preserved. Category counts stay 37 active, 27 superseded, 26 temporal.
- 42 questions / gold answers / key facts / source clauses corrected against existing source Markdown; some questions are rewritten because their original claims cannot be supported by the cited documents.
- 48 benchmark records unchanged. This is **not** a certification that all 90 answers are factually correct.
- The canonical generator `scripts/generate_benchmark_dataset.py` and the JSON plus four JSONL exports are edited consistently. Regeneration will not reintroduce the corrected claims.
- The original 200 training QA rows, `src/lora/` code, registry SHA values and source Markdown are unchanged.

## Evidence and high-impact corrections

| IDs | Finding / repair | Evidence |
| --- | --- | --- |
| `BENCH_SUP_017` | FIT conference 12/03/2024, student report 22/02/2024, both scheduled | [FIT notice](https://www.fit.uet.vnu.edu.vn/ke-hoach-trien-khai-hoi-nghi-svnckh-cap-khoa-nam-hoc-2023-2024/) |
| `BENCH_SUP_018` | AI Institute report 27/02/2025, scheduled meeting 06–15/03/2025 | [UET notice](https://uet.edu.vn/thong-bao-ve-hoat-dong-sinh-vien-nghien-cuu-khoa-hoc-nam-hoc-2024-2025/) |
| `BENCH_TEM_019` | Report 05/03/2026, meeting 23–27/03/2026. Conflicting registration cutoffs are intentionally excluded from the question | [UET notice](https://uet.edu.vn/thong-bao-ve-hoat-dong-sinh-vien-nghien-cuu-khoa-hoc-nam-hoc-2025-2026/) |
| `BENCH_ACT_017` | Scholarship requires **15**, not 14 completed credits per term, subject to separately stated final-term conditions | 2026 scholarship Markdown, Article 7 |
| `BENCH_ACT_020`, `BENCH_SUP_016` | Scholarship governance decision is **4618/QĐ-ĐHQGHN**, superseding **5249/QĐ-ĐHQGHN**; not 3968/2928 | 2024 scholarship Markdown, beginning and Article 18 |
| `BENCH_SUP_013`, `_014`, `_026`, `_027`, `BENCH_TEM_011`, `_012` | Corrected against the 2023 scholarship Appendix of **1388/QĐ-ĐHCN**, not 1459 | `data/raw/uet/markdown/2023/Dinh_muc_hoc_bong_kkht_2023.md` |
| `BENCH_TEM_005`, `_006`, `_007`–`_010` | Corrected incorrect 2022–2023 and 2024–2025 tuition amounts and distinguished admission cohorts | Cited UET Markdown tuition tables |
| `BENCH_ACT_030`, `_031`, `BENCH_TEM_016`, `_017` | Corrected scholarship amounts and made cohort/program explicit | 2025 scholarship Markdown, Article 1 table |
| `BENCH_TEM_022`, `BENCH_ACT_026`, `_027`, `_033`, `_034` | Replaced inferred or ambiguous dates/processes with dates explicitly scheduled in the 2026–2027 academic calendar | 2026 academic-calendar Markdown |
| `BENCH_ACT_024`, `_025`, `_037`, `BENCH_TEM_018`, `_020` | Replaced unsupported legal entitlements, group-size limits, research-topic lists, and award claims with source-backed timetable/reference questions | Corresponding UET notices |

Full 42-item before/after fields, source paths and evidence fragments are in `docs/benchmark_corrections_review_20261027.csv`. Exact substring anchors and corpus SHAs are verified by `tests/test_benchmark_evidence_fixes.py`. These are mechanical checks, not a substitute for final editorial approval.

## Remaining evaluation limitations

1. Many `superseded_rule` items describe historical events or obsolete annual tuition rates, **not proven legal supersession relationships**; category semantics require team agreement.
2. The revised benchmark has 42 changed questions, so scores from the old version must not be compared directly with scores from the corrected version. Freeze a new benchmark SHA/version.
3. The training QA set previously delivered contained templated nonanswers, so it remains blocked independently of this repair. Validate semantic isolation between any replacement train data and this benchmark.
4. Some of the original benchmark contents were already exposed during repair. This cannot be claimed to be a fully untouched held-out test set. Consider an independently authored final test set for unbiased reporting.
5. The 48 unchanged items were checked for structural integrity here, **not individually adjudicated by a reviewer**. Do not mark all 90 gold answers as verified from passing tests alone.

## Files intentionally not changed

- `data/raw/uet/markdown/` and `data/versioning/reviewed_documents.jsonl`
- All LoRA train and `src/lora/` files
- RAG code and configs

## Apply, review and regenerate

Use a new worktree branch and run the bundled installer; it validates old file hashes, payload hashes, Git branch/state, and the full regression suite. Then review the correction table and commit/PR to the benchmark owner. After the PR merges, any cached manifests that pin the old benchmark hash must be regenerated rather than hand-edited.
