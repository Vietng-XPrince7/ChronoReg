# ChronoReg benchmark versioning review | V4

**Status: DRAFT, NOT OWNER-FROZEN, NOT TRAINING-RELEASED.**

This is a reviewable handoff built from the user's real 90-row benchmark snapshot and the October 27 correction evidence artifacts. No gold answers, benchmark labels, or repository files were silently changed. The user's request to take over the other contributor's work is an authorization to perform the audit, **not evidence that all official regulations or effective dates are authenticated**.

## Completed independently

- Rechecked canonical benchmark SHA-256: `333404a93e510ca580a19dc149c2f93587782eb6380def40626deaa05e1036e2`.
- Cross-referenced all **42/42** proposed corrections with actual primary questions and gold answers. This establishes content alignment, not truth or owner sign-off.
- Created a 90-row temporal registry, a 42-row correction review, and a 24-entry document registry (22 documents referenced by the benchmark plus two newly discovered 2023 UET amendments).
- Verified 2022 timetable period 1 `07:00–07:50` against UET-hosted PDF page 2 (link in registry); cross-referenced 4618/QĐ-ĐHQGHN scholarship regulation to VNU official publication.
- Identified **four temporal ambiguity issues** from 2023 tuition adjustment and proposed minimally invasive question clarifications; no gold text is modified.
- Identified the academic-year 2026–27 study plan's five questions as original-PDF provenance pending, even though the uploaded Markdown matches their content.
- Preserved two near-duplicate benchmark questions around the same K67–K70 week-1 event; this should be disclosed or clustered for scoring.

## Blocking issue: retrospective 2022–2023 tuition changes

UET published 2022–2023 tuition schedules in May 2022, then on **12 April 2023** published revised **undergraduate** and **postgraduate** rates, explicitly applying to academic year 2022–2023:

- Original UG: QH-2021 and earlier 1,350,000 VND/month; QH-2022 IT 2,610,000 VND/month; later UET adjustment lists 1,170,000 VND/month for standard/CLC programs (scope against QH-2022 must be verified).
- Original PG: Master cohorts QH-2021 20.25M, QH-2022 30M VND/year; doctoral cohorts QH-2021 33.75M and QH-2022 36M. Later UET adjustment lists masters 17.55M VND/year and doctorate 29.25M VND/year.

Consequently `BENCH_TEM_001`, `_002`, `_005`, `_006` must specify whether they test **the rule as originally issued in 2022** or **the revised rule applied to that academic year**. A year label alone does not resolve this. See `proposed_temporal_question_changes_4_NOT_APPLIED.jsonl`.

Official links:

- [2022 UG original](https://uet.vnu.edu.vn/wp-content/uploads/2022/05/Quy-dinh-dinh-muc-hoc-phi-dao-tao-dai-hoc-nam-hoc-2022-2023.pdf) | [April 2023 UG revision](https://uet.vnu.edu.vn/dieu-chinh-dinh-muc-hoc-phi-dao-tao-dai-hoc-nam-hoc-2022-2023/)
- [2022 PG original](https://uet.vnu.edu.vn/wp-content/uploads/2022/05/Quy-dinh-dinh-muc-hoc-phi-dao-tao-Sau-dai-hoc-nam-hoc-2022-2023.pdf) | [April 2023 PG revision](https://uet.vnu.edu.vn/dieu-chinh-dinh-muc-hoc-phi-dao-tao-sau-dai-hoc-nam-hoc-2022-2023/)
- [VNU 2024 scholarship original](https://www.vnu.edu.vn/upload/2024/10/35731/file/Signed_2024_10_4_QUY%20DINH%20VE%20HOC%20BONG.pdf) | [UET 2022 timetable original](https://tuyensinh.uet.vnu.edu.vn/wp-content/images/QH-2022-I-CQ-C-C.pdf)
- [2025–26 tuition 2080/QĐ-ĐHCN source (UET-hosted PDF)](https://2489013871.e.cdneverest.net/uet.edu.vn/2025/10/Dinh-muc-hoc-phi-nam-hoc-2025-2026.pdf); [UET 2023–24 provisional tuition notice](https://uet.vnu.edu.vn/trien-khai-tam-thu-hoc-phi-trong-hoc-ky-nam-hoc-2022-2023/); [UET faculty post citing 456/KH-ĐHCN](https://fepn.uet.vnu.edu.vn/thong-tin/ke-hoach-bao-ve-kltn-datn-thang-12-2023.html).
- [UET handbook links the 2026–27 study plan](https://handbook.uet.vnu.edu.vn/), original linked Drive PDF not yet authenticated.

## Benchmark freeze conditions

1. Resolve the four retrospective tuition questions; choose a consistent temporal interpretation and update gold answers only when justified.
2. Obtain/verify the UET-hosted original 2026–27 study plan and check the five corrected dates and source SHA-256 lineage.
3. For each of the 22 referenced documents, verify original-document identity, SHA-256 lineage, issued date, applicability, and replacement relation when relevant. The registry intentionally has blank date fields where independent evidence was missing.
4. Record explicit reviewer/owner acceptance for the 42 corrections and review the remaining 48 benchmark records as part of a complete freeze.
5. Reconcile all three category splits after any accepted changes. Produce new immutable hashes and a **new** freeze manifest, rather than modifying the historical V2 logs.
6. Only then approve controlled RAG–LoRA evaluation. LoRA training still requires its **separate** curated-data/leakage release; benchmark freeze is not a training permission.

## Files to propose on the versioning branch

- `docs/benchmark_review/correction_review_42.csv`: 42 dispositions awaiting authorized decisions.
- `docs/benchmark_review/benchmark_temporal_registry_90.csv`: all 90 IDs, category, doc ID, SHA-256, temporal blocker flags.
- `docs/benchmark_review/source_registry_24.csv`: 22 primary document IDs and two discovered amendment records, with URLs and **unknown fields left blank**.
- `docs/benchmark_review/document_version_relations.csv`: documented replacement and amendment relationships.
- `docs/benchmark_review/proposed_temporal_question_changes_4_NOT_APPLIED.jsonl`: suggestion only, not canonical benchmark.
- `docs/benchmark_review/freeze_manifest_DRAFT_BLOCKED.json`: explicit freeze blockers and provenance.
- `scripts/benchmark_freeze_readiness_gate.py`: read-only deterministic gate; no freeze bypass or auto-approval.

The package deliberately does **not** carry the canonical 90 gold answers as a new copy and does not include LoRA staging payloads. Evaluation prompts and gold answers should remain segregated from training data.
