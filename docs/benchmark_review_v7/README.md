# ChronoReg V7 benchmark correction candidate (review only)

This package contains a **provisional preview**, not a benchmark release. It does not modify any repository or authorize LoRA training.

## Candidate contents

- 90 primary benchmark records and the 37/27/26 category splits, generated consistently.
- 2 proposed content corrections: `BENCH_SUP_008` (UET 2024 TTNT standard: 32,000,000 VND/year and 869,000 VND/credit for retakes, correct Article 3) and `BENCH_SUP_012` (foreign-national tuition scoped to actual years/cohorts; no unsupported 996,000 amount).
- 4 historical 2022-tuition questions clarified to reference the *initial* 16 May 2022 rule rather than fees after the 2023 adjustment.
- 4 comparative questions annotated with checksummed supplementary sources (without altering the answer).

The `review_only/` files contain protected **gold answers** and must never be sent to training agents or used as test requests. 10 changes remain `PENDING_OWNER_REVIEW`. `MANIFEST.json` records all source hashes and the review-only status.

**Unresolved:** 2026 original study-plan PDF, all-item factual and time-effectivity signoff, independent approvals, secondary benchmark JSON synchronization, and benchmark freeze. No paths under `data/qa_benchmark/` are replaced by this pack.

Official basis for two content corrections: <https://uet.vnu.edu.vn/dinh-muc-hoc-phi-dao-tao-dai-hoc-nam-hoc-2024-2025/> and the 2025 Markdown source (SHA-256 in the original benchmark), with 2023 tuition amendments at UET's official website.

After human review, implement a separately audited **atomic change** covering the primary, secondary representation, and splits, and update all hashes. Do not copy candidate files directly over the canonical files.
