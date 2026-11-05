# UET curricula source intake (QH-2022 to QH-2026)

Intake date: 2026-11-05. Status: **raw-source staging only; not approved for RAG or LoRA**.

## Structural QA
- 14 programme / proposal source records; 49 out of 49 UET pages returned HTTP 200.
- No structural errors after normalizing Windows newline characters.
- 2 review warnings remain; do not mark these as resolved merely by staging raw files.

## Review warnings
- uet-curriculum-data-science-opening-proposal: Wide variation in table column count; check rowspan/colspan conversion
- AI QH-2022–2024 has original and updated curricula: effective transition requires documentary review

## Documentary boundaries
- Data Science opening proposal: hold out from student-facing answers; manually compare course-table columns with original official HTML.
- AI QH-2022–2024: UET published a 124-credit page dated 2022-10-17 and a 123-credit page dated 2024-01-18.
  Publication dates are **not** verified legal/effective transition dates. Retain both versions.
- Source URLs: https://uet.edu.vn/chuong-trinh-dao-tao-nganh-tri-tue-nhan-tao-3/ and
  https://uet.edu.vn/chuong-trinh-dao-tao-nganh-tri-tue-nhan-tao-6/.
- Keep opening proposals and out-of-range cohorts excluded unless documented evidence changes scope.

## Next gate
Verify course identifiers, course names, credit totals, elective accounting,
prerequisites, cohort applicability and approved edition transitions against primary sources.
Do not alter approved_relations.jsonl, reviewed_documents.jsonl, the benchmark or LoRA training files based on this intake.

Files: `data/raw/uet/markdown/curricula/` and `data/raw/uet/curricula/`.
