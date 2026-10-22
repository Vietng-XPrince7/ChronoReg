# Suggested first reviews from the supplied corpus

These are **unverified candidates**. They illustrate why the registry separates document dates, academic years and relationships. Validate against the official source before adding approved metadata or edges.

## 1. Study plan 2023–2024

`2023/Ke_hoach_hoc_tap_2023.md` includes a heading for academic year **2023–2024** and extracted document number **456/KH-ĐHCN**, with an OCR-rendered date around **05/09/2023**. Check the PDF for correct date, version and schedule tables, then approve the metadata. Folder year alone is not sufficient.

## 2. Tuition 2023–2024

`2023/Ke_hoach_thu_hoc_phi_2023.md` labels tuition amounts as **dự kiến** (provisional). It must not become the authoritative final tuition decision merely because it contains numbers. `2023/Dieu_chinh_hoc_phi_2023.md` cites **279/QĐ-ĐHCN dated 17/02/2024**, but its article concerns lists of specific students; do not create a global `supersedes` edge. The separately cited 279 decision is a high-priority missing source to retrieve and validate.

## 3. Scholarship decision 2026

`2026/Quy_dinh_xet_hoc_bong_kkht_2026.md` contains **1931/QĐ-ĐHCN dated 07/08/2026** and states that the regulation applies from semester I of 2026–2027. Its effective-date clause says “kể từ ngày ký”. The same clause says it replaces previous documents **without enumerating them in the extracted excerpt**: no exact superseded-document edge should be approved yet. Check the official decision and the scope before reviewing any interval or relationship.

## 4. Research rules and policy applicability

`Quy_dinh_nckh_2022.md` is a list/index of links to regulations with different issue years; it is not itself a regulation enacted in 2022. `2022/Danh_sach_de_tai_nckh_2022.md` is a research project list, not an enforceable research rule. Collect the actual decisions linked in the index before treating them as rule versions.

## 5. Protect personal data

`2022/Hoc_bong_2022.md` is a named scholarship recipient list, not the generally applicable scholarship eligibility rule. `2026/Danh_sach_phong_ban.md` contains staff directory data. These must not be silently included in general-purpose QA/RAG training material.
