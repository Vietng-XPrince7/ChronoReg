# UET version management - review batch 3

Scope: verify two tuition regulations for academic year **2024-2025** (undergraduate and postgraduate). Only the version registry, two source-derived Markdown files, and versioning tests are modified.

| Source | Date fields | Applicability | Official evidence |
|---|---|---|---|
| UET undergraduate tuition 2024-2025 | `issued_date=null`, `effective_from=null` | Academic year 2024-2025, separated by undergraduate cohort and program | https://uet.vnu.edu.vn/dinh-muc-hoc-phi-dao-tao-dai-hoc-nam-hoc-2024-2025/ |
| UET postgraduate tuition 2024-2025 | `issued_date=null`, `effective_from=null` | Academic year 2024-2025, master's vs PhD and admission cohort | https://uet.vnu.edu.vn/dinh-muc-hoc-phi-dao-tao-sau-dai-hoc-nam-hoc-2024-2025/ |

These are **original UET web publications**, not independently authenticated signed PDF decisions. Publication date is not assumed to equal the signature date. The source describes only the *academic year*, not an exact calendar effective interval. No open-ended validity or supersession is asserted.

## Source cleanup

- Fixed PDF-to-Markdown table cells that split cohorts across multiple rows, affecting year/cohort-dependent extraction.
- Repaired the 2024 postgraduate tuition rows for master's cohorts (2021 and before / 2022-2024), preserving the published amounts: VND 24.6m / 33m per year and VND 767k / 1.076m per credit (respectively).
- Repaired a split 2022 cohort name in the undergraduate tuition and a broken 2022 TT23 table header. No tuition figures changed by this batch.
- Removed page-number/footer artifacts and a split word from the source-derived Markdown; original official URLs remain present.

## Known gaps / do not silently approve

- 2022-2023 **original** tuition decisions have later UET tuition adjustment decisions. These later adjustments are not in the 27-document corpus. Before approving 2022 tuition for policy QA, collect the adjusted decisions and record applicability by cohort, program and academic year.
- `review_status=verified_against_source` covers the scoped year and corrected passages only; it is not a claim that every table in the corpus has legal validity for any as-of date.
- No data from RAG, LoRA, benchmark or shared schema files was modified.

## Verification

Run `py -m pytest -q tests/test_versioning.py tests/test_versioning_review_batch2.py tests/test_versioning_review_batch3.py`; then `py -m src.versioning.cli build` and `py -m src.versioning.cli export-chunks`.

The expected registry after application: `total=27`, `verified=8`, `policy_qa_ready=8`, `approved_relations=0`.
