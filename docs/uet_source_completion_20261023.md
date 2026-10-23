# UET research and tuition source completion (23 October 2026)

## Scope

Supplement the ChronoReg **source corpus** without altering QA approvals, benchmark, RAG, LoRA weights, existing review ledgers or shared schema.

Four research notices were added as Markdown. The 2023–2024 individual tuition adjustment already existed (`2023/Dieu_chinh_hoc_phi_2023.md`), so it was NOT duplicated. Its official-source HTML-to-PDF snapshot was archived as secondary evidence. None of these additions is a full signed normative policy replacing a prior version.

## Source cross-check

| Academic year | Material | Issuer/scope | Evidence |
| --- | --- | --- | --- |
| 2023–2024 | SVNCKH implementation schedule | Faculty of IT only | [Official faculty announcement](https://www.fit.uet.vnu.edu.vn/ke-hoach-trien-khai-hoi-nghi-svnckh-cap-khoa-nam-hoc-2023-2024/), locally preserved converted PDF |
| 2024–2025 | Research conference schedule | Institute of AI only | [Official UET institute announcement](https://uet.edu.vn/thong-bao-ve-hoat-dong-sinh-vien-nghien-cuu-khoa-hoc-nam-hoc-2024-2025/), locally preserved converted PDF |
| 2025–2026 | Research conference schedule | Institute of AI only | [Official UET institute announcement](https://uet.edu.vn/thong-bao-ve-hoat-dong-sinh-vien-nghien-cuu-khoa-hoc-nam-hoc-2025-2026/), locally preserved converted PDF |
| 2025–2026 | Conference notice No.1 | UET school level | [Official 3-page PDF](https://www.fit.uet.vnu.edu.vn/wp-content/uploads/2026/01/Signed.Signed.Signed.2025.10.-TB1-TrienkhaicongtacSVNCKH-2026.pdf), selected excerpts only; the PDF's header has unfilled number/date fields |
| 2023–2024 | Tuition adjustment for named students | UET, individual cases | [Official UET decision content](https://uet.vnu.edu.vn/dieu-chinh-bo-sung-hp-trong-nam-hoc-2023-2024/), existing Markdown, locally preserved converted PDF |

The two missing **full decision texts** are 279/QĐ-ĐHCN (17 February 2024) and 447/QĐ-ĐHCN (7 March 2025). Both numbers and their stated topics are supported by official UET citations, but the full primary documents could not be retrieved. Do not invent their effective periods, tables of fees, amended clauses, or supersession relationships. See `data/versioning/unresolved_primary_decisions_20261023.json`.

## Integrity rules

1. PDFs under `source_archives/html_to_pdf/` are derivative snapshots of official HTML, **not signed originals**; each is preserved byte-for-byte from the user's existing document archive and its SHA-256 is recorded in the source ledger.
2. New Markdown content is extracted/normalized from official sources and local archived copies. It is usable for source discovery and manual review; **not approved QA**.
3. `reviewed_documents.jsonl`, `publication_holds.jsonl`, and `approved_relations.jsonl` remain unchanged. Hence the new Markdown rows stay `unreviewed` and `policy_qa_ready=false` in a registry build.
4. The Institute of AI 2025–2026 page contains differing schedule descriptions (25 February registration in table, 15 February in paragraph). Both are faithfully retained; do not silently resolve this discrepancy.
5. The 2023 tuition adjustment applies to a list of individual students. Its attachment contains personal data and is deliberately omitted from this dataset.
6. Only the 2025–2026 notice is at UET school level. Other notices cannot be generalized outside their faculty/institute.
7. Do not treat `academic_year` as the legal issue date, or the web-posted date as the legal signing date.

## Applying

Use `python Apply-UET-Source-Supplement.py --repo C:\HaiAnh\ChronoReg-LoRA` from an extracted package. This only adds files. The installer performs dry-run registry validation using temporary generated outputs, preserving the user's current results and QA review decisions.

## Official website evidence acceptance

When a complete signed decision is unavailable, an authentic UET
website announcement is acceptable evidence for facts explicitly
published in that announcement.

The review must retain the exact URL, academic year, issuing unit,
scope, and any contradictions in the published content.

An announcement does not establish unstated legal effective dates,
complete decision contents, university-wide applicability, or
supersession relationships.

Source acceptance does not automatically approve training QA.
Each QA answer still requires content review and benchmark isolation.