# UET version registry: review batch 2

This batch updates **only UET versioning metadata and four source-derived Markdown documents**. It makes no changes to `models.py`, `docs/schema.md`, RAG, LoRA or evaluation implementations.

## Verified against official sources

| Document | Issued | Academic year | Calendar effectivity | Source and scope |
|---|---|---|---|---|
| 1388/QĐ-ĐHCN, scholarship rates | 2023-12-21 | 2023-2024 | Not asserted | UET official 1-page scholarship appendix; rates by degree program and admission cohort |
| 4618/QĐ-ĐHQGHN, scholarship management | 2024-10-07 | Not year-specific | From date of signature 2024-10-07; **end not established** | VNU-wide (not a UET tuition/scholarship rate) |
| 2339/QĐ-ĐHCN, scholarship rates | 2025-10-27 | 2025-2026 | Not asserted | UET official article; cited decision number confirmed by subsequent UET scholarship awards |
| 2377/QĐ-ĐHCN, tuition appendix | 2026-09-21 | 2026-2027 | Not asserted | UET official article + 3-page official PDF |
| 1931/QĐ-ĐHCN, scholarship assessment rules | 2026-08-07 | **2026-2027** | From signature 2026-08-07; **end not established** | UET official article + 3-page signed-rule appendix; effective date and academic-year applicability are different concepts |

The 2025-2026 tuition document already reviewed in batch 1 remains untouched. After this batch, **6 of the 27 scoped documents** have reviewed metadata, and **0 approved document-level replacement relationships** exist.

## Explicit legal/semantic constraints

1. The 2026 scholarship rule states that it takes effect from signature and applies from semester I of **2026-2027**, while using results from semester II of **2025-2026**. The latter is a reference period, *not* the regulation's academic year.
2. The 2026 scholarship rule generally mentions replacing previously issued documents; it does not identify a particular earlier UET document number. We therefore do **not** approve a named supersession edge.
3. The 2024 VNU scholarship rule expressly replaces decision **5249/QĐ-ĐHQGHN (2014)**, which is not part of the 27-document corpus. We do not invent a graph endpoint.
4. No unknown end-of-validity is mapped to `open_ended_verified=true`. Only effective start dates expressly supported by the source are stored.
5. The source article for scholarship 2025 cites `2113/QĐ-ĐHCN` regarding tuition 2025-2026 in one recital although the UET 2025-2026 tuition decision is `2080/QĐ-ĐHCN`; that recital is **not** used to establish a cross-document authority link. No auto-correction of the official article is made.
6. Markdowns previously contained PDF table extraction artifacts; corrected rows were transcribed from the official UET pages/PDF. Four changed files are protected by old/new SHA-256 manifests and the previous versions are backed up before replacement.

## Source URLs

- Scholarship rates 2023: https://www.uet.edu.vn/wp-content/uploads/2023/12/Dinh-muc-HB-KKHT-nam-hoc-2023-2024.pdf
- VNU scholarship policy 2024: https://uet.edu.vn/wp-content/uploads/2024/10/Signed.Signed.Signed.2024_10_4_QUY-DINH-VE-HOC-BONG.pdf
- UET scholarship rate 2025: https://uet.edu.vn/quy-dinh-muc-hoc-bong-khuyen-khich-hoc-tap-cho-sinh-vien-dai-hoc-he-chinh-quy-trong-nam-hoc-2025-2026/
- UET decision cross-reference to 2339: https://uet.edu.vn/cap-hoc-bong-khuyen-khich-hoc-tap-trong-hoc-ky-i-nam-hoc-2025-2026-cho-sinh-vien/
- Tuition 2026 decision: https://uet.edu.vn/quy-dinh-dinh-muc-hoc-phi-cac-ctdt-nam-hoc-2026-2027/
- Tuition 2026 PDF: https://2679558515.e.cdneverest.net/uet.edu.vn/2026/09/dinh-muc-hoc-phi-nam-hoc-2026-2027_tb-nguoi-hoc.pdf
- UET scholarship policy 2026 decision: https://uet.edu.vn/quy-dinh-ve-viec-xet-cap-hoc-bong-khuyen-khich-hoc-tap-tai-truong-dai-hoc-cong-nghe/
- UET scholarship policy 2026 PDF: https://2489013871.e.cdneverest.net/uet.edu.vn/2026/08/Quy-dinh-Hoc-bong-KKHT-UET-2026.pdf

## Remaining work

21 documents await complete review, including schedules, research regulations/index pages, 2022 tuition appendices and older document-year ambiguity. Do not mark those as verified solely because they have a year in their folder. No dataset evaluation questions, RAG pipeline, LoRA training or shared-schema modifications are included in this batch.
