# Tuấn curricula intake | QA and handoff

Review date: 2026-11-13. **Staged source evidence, not production QA approval.**

## Contents and deduplication

- Uploaded 6 ZIP files: the combined 2022–2026 archive and 5 per-year archives. The per-year files are exact subsets of the combined archive.
- **130 per-year Markdown occurrences**, **54 distinct content SHA-256 values**, **76 duplicate occurrences suppressed**.
- **53 distinct curriculum/source-section files** staged in `data/raw/uet/markdown/curricula/tuan_2022_2026/`.
- **54 untouched original Markdown files** preserved in `data/raw/uet/curricula/tuan_2022_2026/original/`, including 1 excluded admissions guide.
- No existing source document, previous curricula data, approved relations or benchmarks are overwritten.

## Section types

- `admissions_guidance`: 1
- `curriculum_content`: 14
- `implementation`: 6
- `learning_outcomes`: 17
- `overview`: 16

## Program code hints extracted from filenames (not verified)

- `cntt`: 7
- `cntt_clc`: 3
- `cntt_nhat_ban`: 2
- `httt`: 5
- `khmt`: 5
- `ktmt`: 4
- `ktrb`: 7
- `ktvt`: 10
- `mmtthdl`: 1
- `mmtttdl`: 9
- `unclassified`: 1

## Automated content-review signals (non-exclusive)

- `filename_mentions_2019_do_not_infer_cohort_2022`: 6 document(s)
- `html_line_breaks_in_table`: 23 document(s)
- `multiple_table_header_widths`: 13 document(s)
- `not_curriculum`: 1 document(s)
- `official_source_url_missing_in_upload`: 54 document(s)
- `suspected_ocr_corruption`: 7 document(s)

## Outstanding review and release gates

1. **Primary-source provenance:** Most uploaded snippets have no UET official URL or PDF identifier. Find official corresponding pages or decisions and record per-record citation. Do not invent them.
2. **Cohort applicability:** The year folder is the collector's folder, not necessarily a QH year; `2019_trodi`, `2022_tro_di` and `2025_tro_di` are filename hints until matched with UET's authorized curriculum pages.
3. **Quality:** Several extracted tables have split words/HTML `<br>` breaks; some 2025/2026 outcome sections show apparent OCR corruption. Compare with original source before course-level QA.
4. **Out-of-scope item:** `huong_dan_dang_ky_xet_tuyen_2024.md` is an admissions guide, kept only among untouched originals, not in curriculum searchable content.
5. **Versioning:** Approve neither supersession nor effective dates simply from a year label. No changes to `data/versioning/reviewed_documents.jsonl`, `approved_relations.jsonl`, benchmark or LoRA.
6. All new normalized files are `retrieval_eligible: false`, `review_status: needs_human_review`. The existing core registry categorizes these as `other`; standard reviewed-only policy RAG export excludes them.

## Suggested repository branch

`data/uet-tuan-curricula-2022-2026` targeting current `origin/main`; merge only as raw evidence with the review hold intact.
