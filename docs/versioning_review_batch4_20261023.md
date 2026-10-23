# ChronoReg – final 19-document source review (2026-10-23)

Scope: the remaining 19 documents in the 27-file UET subset (2022–2026). No RAG, LoRA, evaluation, `models.py`, or shared `docs/schema.md` changes.

## Outcome

- All 19 remaining input files have SHA-256-bound review/disposition records.
- 15 additional files have independently traceable UET primary-source metadata (not full text/legal validity verification).
- 4 remain unverified because the matching original is unavailable, the URL/year mismatches, or the source is too noisy.
- 14 source entries have an explicit publication hold (obsolete original rates, corrupt table extraction, or informational indexes).
- Version registry on the 27-document scoped corpus: 23 source-verified metadata records, 10 year-scoped QA ready, 0 approved replacement relationships.
- A document that is verified for origin and academic year is NOT automatically legally effective for arbitrary calendar dates.

## Review dispositions

- `catalog_only`: 6
- `historical_hold`: 3
- `metadata_verified`: 2
- `needs_original`: 2
- `quality_hold`: 5
- `source_mismatch`: 1

## High-priority evidence and limitations

1. Original 2022–2023 undergraduate and postgraduate tuition PDFs have later official UET adjustment decisions, separately available at https://uet.vnu.edu.vn/dieu-chinh-dinh-muc-hoc-phi-dao-tao-dai-hoc-nam-hoc-2022-2023/ and https://uet.vnu.edu.vn/dieu-chinh-dinh-muc-hoc-phi-dao-tao-sau-dai-hoc-nam-hoc-2022-2023/. They are recorded as `historical_hold` until the adjustments are ingested and scoped.
2. Extended-time postgraduate study PDF at https://uet.vnu.edu.vn/wp-content/uploads/2022/05/Quy-dinh-dinh-muc-hoc-phi-dao-tao-Sau-dai-hoc-trong-thoi-gian-keo-dai.pdf states it replaces Decision 827/QĐ-ĐT (2016). The 2016 target is not in the 27-file repository, so no approved relation is invented.
3. The 2023–2024 plan `456/KH-ĐHCN` is indirectly referenced by an official UET faculty page, but the PDF used to produce the local Markdown was not independently retrieved in this review. Its table contains extraction damage, so it remains unreviewed.
4. The 2023 tuition collection file links to a page for 2022–2023 while its Markdown header says 2023–2024; held for source mismatch.
5. The individual student tuition-adjustment page and scholarship recipient lists do not establish general rules, and may carry personal data. They are catalogued but not released for general policy QA.
6. `Quy_dinh_nckh_2022.md` is an index of many different acts, not one decision from 2022. Subordinate linked files must be versioned as separate documents.
7. Campus calendars with damaged Markdown tables are withheld even when their year and source PDF are confirmed. Their PDF originals should be used to repair cells before releasing.
8. As-of-date validity is intentionally unknown unless a source explicitly supports an interval; no automatic open-ended effectiveness is asserted.

## Traceability

- `data/versioning/batch4_review_ledger.jsonl` / `.csv`: audit result for each of the 19 source documents.
- `data/versioning/publication_holds.jsonl`: SHA-bound holds used by the policy QA gate.
- `data/versioning/reviewed_documents.jsonl`: 15 source-reviewed metadata entries appended after the previous eight.
- `tests/test_versioning_review_batch4.py`: regression coverage for SHA-bound holds and immutable review dispositions.

## Full status of remaining files

| File | Disposition | Further action |
|---|---|---|
| `2022/Danh_sach_de_tai_nckh_2022.md` | `catalog_only` | None for catalog purposes; retain provenance. |
| `2022/Dinh_muc_hoc_phi_dao_tao_dai_hoc_2022.md` | `historical_hold` | Ingest the adjusting decision and verify supersession scope before release. |
| `2022/Dinh_muc_hoc_phi_dao_tao_dai_hoc_ct_clc_tt_23_2022.md` | `historical_hold` | Ingest the adjusting decision and verify supersession scope before release. |
| `2022/Dinh_muc_hoc_phi_dao_tao_sau_dai_hoc_2022.md` | `historical_hold` | Ingest the adjusting decision and verify supersession scope before release. |
| `2022/Dinh_muc_hoc_phi_dao_tao_sau_dai_hoc_trong_thoi_gian_keo_dai_2022.md` | `metadata_verified` | Metadata verified for year-scoped access; legal validity by date remains separate. |
| `2022/Hoat_dong_nckh_2022.md` | `metadata_verified` | Metadata verified for year-scoped access; legal validity by date remains separate. |
| `2022/Hoc_bong_2022.md` | `catalog_only` | None for catalog purposes; retain provenance. |
| `2022/Ke_hoach_hoc_tap_2022.md` | `quality_hold` | Repair original PDF table alignment and confirm all extracted rows. |
| `2023/Dieu_chinh_hoc_phi_2023.md` | `catalog_only` | None for catalog purposes; retain provenance. |
| `2023/Ke_hoach_hoc_tap_2023.md` | `needs_original` | Obtain and verify matching original UET source PDF / announcement. |
| `2023/Ke_hoach_thu_hoc_phi_2023.md` | `source_mismatch` | Obtain and verify matching original UET source PDF / announcement. |
| `2024/Ke_hoach_hoc_tap_2024.md` | `quality_hold` | Repair original PDF table alignment and confirm all extracted rows. |
| `2025/Ke_hoach_hoc_tap_2025.md` | `quality_hold` | Repair original PDF table alignment and confirm all extracted rows. |
| `2026/Ke_hoach_hoc_tap_2026.md` | `needs_original` | Obtain and verify matching original UET source PDF / announcement. |
| `2026/cac_nganh_ap_dung_hoc_bong_theo_nghi_dinh_179_2026.md` | `catalog_only` | None for catalog purposes; retain provenance. |
| `Danh_muc_nckh_2022.md` | `catalog_only` | None for catalog purposes; retain provenance. |
| `Quy_dinh_nckh_2022.md` | `catalog_only` | None for catalog purposes; retain provenance. |
| `Quy_dinh_nop_hoc_phi_2021.md` | `quality_hold` | Repair original PDF table alignment and confirm all extracted rows. |
| `Thoi_khoa_bieu_hoc_ki_I_2022_2023.md` | `quality_hold` | Repair original PDF table alignment and confirm all extracted rows. |
