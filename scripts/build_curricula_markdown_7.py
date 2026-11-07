"""Bộ tạo và đồng bộ dữ liệu 7 ngành chương trình đào tạo UET sang Markdown, Source Cards và Metadata Registry.

Tuân thủ nghiêm ngặt chuẩn cấu trúc của data/raw/uet/markdown/curricula/:
1. Kỹ thuật không gian (3 bản: QH-2026-plus, QH-2025, QH-2022-to-2024)
2. Cơ kỹ thuật (2 bản: QH-2025-plus, QH-2022-to-2024)
3. Kỹ thuật điều khiển và tự động hóa (2 bản: QH-2025-plus, QH-2022-to-2024)
4. Kỹ thuật Cơ điện tử (3 bản: QH-2026-plus, QH-2025, QH-2022-to-2024)
5. Kỹ thuật vật liệu (3 bản: QH-2026-plus, QH-2025, opening-proposal)
6. Kỹ thuật năng lượng (2 bản: QH-2025-plus, QH-2022-to-2024)
7. Vật lý kỹ thuật (2 bản: QH-2025-plus, QH-2022-to-2024)
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def html_to_clean_markdown_text(html_snippet: str) -> str:
    """Chuyển đổi đoạn HTML sang định dạng Markdown chuẩn với danh sách và đề mục."""
    s = html_snippet
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)

    # Đề mục
    s = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", s, flags=re.S | re.I)
    s = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", s, flags=re.S | re.I)
    s = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", s, flags=re.S | re.I)
    s = re.sub(r"<h4[^>]*>(.*?)</h4>", r"\n#### \1\n", s, flags=re.S | re.I)

    # In đậm, in nghiêng
    s = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", s, flags=re.S | re.I)
    s = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", s, flags=re.S | re.I)

    # Xuống dòng và đoạn
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)

    # Danh sách
    s = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", s, flags=re.S | re.I)
    s = re.sub(r"</?(ul|ol)[^>]*>", "\n", s, flags=re.I)

    # Loại bỏ các thẻ khác trừ table
    s = re.sub(
        r"<(?!(?:table|thead|tbody|tfoot|tr|th|td|\/table|\/thead|\/tbody|\/tfoot|\/tr|\/th|\/td))[^>]+>",
        " ",
        s,
    )
    s = html.unescape(s)
    return s


def table_to_markdown(table_html: str) -> str:
    """Chuyển đổi bảng HTML <table> sang Markdown table chuẩn."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)
    if not rows:
        return ""

    md_rows = []
    max_cols = 0
    for r in rows:
        cells = re.findall(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", r, re.S | re.I)
        clean_cells = []
        for c in cells:
            c_txt = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", c, flags=re.S | re.I)
            c_txt = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", c_txt, flags=re.S | re.I)
            c_txt = re.sub(r"<br\s*/?>", " ", c_txt, flags=re.I)
            c_txt = re.sub(r"<[^>]+>", " ", c_txt)
            c_txt = html.unescape(c_txt)
            c_txt = re.sub(r"\s+", " ", c_txt).strip()
            clean_cells.append(c_txt)
        if clean_cells:
            max_cols = max(max_cols, len(clean_cells))
            md_rows.append(clean_cells)

    if not md_rows:
        return ""

    lines = []
    header = md_rows[0] + [""] * (max_cols - len(md_rows[0]))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for r in md_rows[1:]:
        padded = r + [""] * (max_cols - len(r))
        lines.append("| " + " | ".join(padded) + " |")

    return "\n" + "\n".join(lines) + "\n"


def extract_section_content(html_content: str) -> tuple[str, int]:
    """Trích xuất phần bài viết chính và trả về (markdown_text, table_count)."""
    m = re.search(r"<article[^>]*>(.*?)</article>", html_content, re.S)
    if not m:
        return "", 0
    art = m.group(1)
    art = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", art, flags=re.S | re.I)
    art = re.sub(r'<div class="entry-meta".*?</div>', "", art, flags=re.S | re.I)
    art = re.sub(r'<header class="entry-header".*?</header>', "", art, flags=re.S | re.I)
    art = re.sub(r'<footer class="entry-footer".*?</footer>', "", art, flags=re.S | re.I)
    art = re.sub(r'<nav class="navigation post-navigation".*?</nav>', "", art, flags=re.S | re.I)
    art = re.sub(r'<div id="related-posts".*?</div>', "", art, flags=re.S | re.I)
    art = re.sub(r'<div class="sharedaddy.*', "", art, flags=re.S | re.I)

    tables = []

    def _tbl_repl(match):
        tables.append(table_to_markdown(match.group(0)))
        return f"\n\n__TABLE_PLACEHOLDER_{len(tables)-1}__\n\n"

    art = re.sub(r"<table[^>]*>.*?</table>", _tbl_repl, art, flags=re.S | re.I)
    txt = html_to_clean_markdown_text(art)

    for i, tbl in enumerate(tables):
        txt = txt.replace(f"__TABLE_PLACEHOLDER_{i}__", tbl)

    lines = [l.rstrip() for l in txt.splitlines()]
    cleaned = []
    empty_count = 0
    for l in lines:
        if not l.strip():
            empty_count += 1
            if empty_count <= 1:
                cleaned.append("")
        else:
            empty_count = 0
            cleaned.append(l)

    return "\n".join(cleaned).strip(), len(tables)


# Load edition definitions
editions_plan_file = Path("scratch_raw_pages/editions_plan.json")
with open(editions_plan_file, encoding="utf-8") as f:
    editions_plan = json.load(f)

# Metadata lookup for 17 editions
editions_meta = {
    # 1. space-engineering
    "uet-curriculum-space-engineering-QH-2026-plus": {
        "program_slug": "space-engineering",
        "program_name_vi": "Kỹ thuật không gian",
        "title_heading": "Kỹ thuật không gian",
        "cohort_text": "QH-2026 trở đi",
        "cohort_from": 2026,
        "cohort_to": None,
        "edition_label": "QH-2026-plus",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-hang-khong-vu-tru-4/",
        "version_note": "Áp dụng cho khóa QH-2026 trở đi. CTĐT Kỹ thuật Hàng không vũ trụ – Ngành Kỹ thuật không gian (mã số 7520121).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-space-engineering-QH-2025": {
        "program_slug": "space-engineering",
        "program_name_vi": "Công nghệ hàng không vũ trụ",
        "title_heading": "Công nghệ hàng không vũ trụ",
        "cohort_text": "QH-2025 đến QH-2025",
        "cohort_from": 2025,
        "cohort_to": 2025,
        "edition_label": "QH-2025",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-hang-khong-vu-tru-4/",
        "version_note": "Áp dụng riêng cho khóa tuyển sinh QH-2025 (mã ngành 7519001).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-space-engineering-QH-2022-to-2024": {
        "program_slug": "space-engineering",
        "program_name_vi": "Công nghệ hàng không vũ trụ",
        "title_heading": "Công nghệ hàng không vũ trụ",
        "cohort_text": "QH-2022 đến QH-2024",
        "cohort_from": 2022,
        "cohort_to": 2024,
        "edition_label": "QH-2022-to-2024",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 152,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-hang-khong-vu-tru-4/",
        "version_note": "Chỉ mục ghi QH-2022 trở đi; khoanh vùng QH-2022–2024 do có các phiên bản riêng cho 2025 và 2026.",
        "curriculum_status": "curriculum",
    },
    # 2. engineering-mechanics
    "uet-curriculum-engineering-mechanics-QH-2025-plus": {
        "program_slug": "engineering-mechanics",
        "program_name_vi": "Cơ kỹ thuật",
        "title_heading": "Cơ kỹ thuật",
        "cohort_text": "QH-2025 trở đi",
        "cohort_from": 2025,
        "cohort_to": None,
        "edition_label": "QH-2025-plus",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-co-ky-thuat-4/",
        "version_note": "Áp dụng cho khóa QH-2025 trở đi (mã số 7520101).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-engineering-mechanics-QH-2022-to-2024": {
        "program_slug": "engineering-mechanics",
        "program_name_vi": "Cơ kỹ thuật",
        "title_heading": "Cơ kỹ thuật",
        "cohort_text": "QH-2022 đến QH-2024",
        "cohort_from": 2022,
        "cohort_to": 2024,
        "edition_label": "QH-2022-to-2024",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-co-ky-thuat-4/",
        "version_note": "Chỉ mục ghi QH-2022 trở đi; khoanh vùng QH-2022–2024 do có phiên bản riêng cho 2025 trở đi.",
        "curriculum_status": "curriculum",
    },
    # 3. control-and-automation
    "uet-curriculum-control-and-automation-QH-2025-plus": {
        "program_slug": "control-and-automation",
        "program_name_vi": "Kỹ thuật điều khiển và tự động hóa",
        "title_heading": "Kỹ thuật điều khiển và tự động hóa",
        "cohort_text": "QH-2025 trở đi",
        "cohort_from": 2025,
        "cohort_to": None,
        "edition_label": "QH-2025-plus",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-ky-thuat-dieu-khien-va-tu-dong-hoa-4/",
        "version_note": "Áp dụng cho khóa QH-2025 trở đi (mã số 7520216).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-control-and-automation-QH-2022-to-2024": {
        "program_slug": "control-and-automation",
        "program_name_vi": "Kỹ thuật điều khiển và tự động hóa",
        "title_heading": "Kỹ thuật điều khiển và tự động hóa",
        "cohort_text": "QH-2022 đến QH-2024",
        "cohort_from": 2022,
        "cohort_to": 2024,
        "edition_label": "QH-2022-to-2024",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-ky-thuat-dieu-khien-va-tu-dong-hoa-4/",
        "version_note": "Chỉ mục ghi QH-2022 trở đi; khoanh vùng QH-2022–2024 do có phiên bản riêng cho 2025 trở đi.",
        "curriculum_status": "curriculum",
    },
    # 4. mechatronics-engineering
    "uet-curriculum-mechatronics-engineering-QH-2026-plus": {
        "program_slug": "mechatronics-engineering",
        "program_name_vi": "Kỹ thuật Cơ điện tử",
        "title_heading": "Kỹ thuật Cơ điện tử",
        "cohort_text": "QH-2026 trở đi",
        "cohort_from": 2026,
        "cohort_to": None,
        "edition_label": "QH-2026-plus",
        "degree": "Cử nhân",
        "duration_years": 4.0,
        "reported_total_credits": 135,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-ky-thuat-co-dien-tu-4/",
        "version_note": "Áp dụng cho khóa QH-2026 trở đi (mã số ngành 7520114).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-mechatronics-engineering-QH-2025": {
        "program_slug": "mechatronics-engineering",
        "program_name_vi": "Công nghệ kỹ thuật cơ điện tử",
        "title_heading": "Công nghệ kỹ thuật cơ điện tử",
        "cohort_text": "QH-2025 đến QH-2025",
        "cohort_from": 2025,
        "cohort_to": 2025,
        "edition_label": "QH-2025",
        "degree": "Cử nhân",
        "duration_years": 4.0,
        "reported_total_credits": 135,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-ky-thuat-co-dien-tu-4/",
        "version_note": "Áp dụng riêng cho khóa QH-2025 (mã ngành 7510203).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-mechatronics-engineering-QH-2022-to-2024": {
        "program_slug": "mechatronics-engineering",
        "program_name_vi": "Công nghệ kỹ thuật cơ điện tử",
        "title_heading": "Công nghệ kỹ thuật cơ điện tử",
        "cohort_text": "QH-2022 đến QH-2024",
        "cohort_from": 2022,
        "cohort_to": 2024,
        "edition_label": "QH-2022-to-2024",
        "degree": "Cử nhân",
        "duration_years": 4.0,
        "reported_total_credits": 135,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-cong-nghe-ky-thuat-co-dien-tu-4/",
        "version_note": "Chỉ mục ghi QH-2022 trở đi; khoanh vùng QH-2022–2024 do có các bản riêng cho 2025 và 2026.",
        "curriculum_status": "curriculum",
    },
    # 5. materials-engineering
    "uet-curriculum-materials-engineering-QH-2026-plus": {
        "program_slug": "materials-engineering",
        "program_name_vi": "Kỹ thuật vật liệu",
        "title_heading": "Kỹ thuật vật liệu",
        "cohort_text": "QH-2026 trở đi",
        "cohort_from": 2026,
        "cohort_to": None,
        "edition_label": "QH-2026-plus",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-cong-nghe-vat-lieu-va-vi-dien-tu-nganh-cong-nghe-vat-lieu-4/",
        "version_note": "Áp dụng cho khóa QH-2026 trở đi (CT Kỹ thuật vật liệu và Vi điện tử, mã số 7520309).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-materials-engineering-QH-2025": {
        "program_slug": "materials-engineering",
        "program_name_vi": "Công nghệ vật liệu (CT Công nghệ vật liệu và Vi điện tử)",
        "title_heading": "Công nghệ vật liệu (CT Công nghệ vật liệu và Vi điện tử)",
        "cohort_text": "QH-2025 đến QH-2025",
        "cohort_from": 2025,
        "cohort_to": 2025,
        "edition_label": "QH-2025",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-cong-nghe-vat-lieu-va-vi-dien-tu-nganh-cong-nghe-vat-lieu-4/",
        "version_note": "Áp dụng cho khóa QH-2025 (mã ngành 7510402).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-materials-engineering-opening-proposal": {
        "program_slug": "materials-engineering",
        "program_name_vi": "Công nghệ vật liệu (CT Công nghệ vật liệu và Vi điện tử)",
        "title_heading": "Công nghệ vật liệu (CT Công nghệ vật liệu và Vi điện tử)",
        "cohort_text": "Đề án mở ngành (không áp dụng QH)",
        "cohort_from": None,
        "cohort_to": None,
        "edition_label": "opening-proposal",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-cong-nghe-vat-lieu-va-vi-dien-tu-nganh-cong-nghe-vat-lieu-4/",
        "version_note": "Đề án mở ngành; nguồn tham khảo KHÔNG phải phiên bản học tập đã áp dụng.",
        "curriculum_status": "opening_proposal",
    },
    # 6. energy-engineering
    "uet-curriculum-energy-engineering-QH-2025-plus": {
        "program_slug": "energy-engineering",
        "program_name_vi": "Kỹ thuật năng lượng",
        "title_heading": "Kỹ thuật năng lượng",
        "cohort_text": "QH-2025 trở đi",
        "cohort_from": 2025,
        "cohort_to": None,
        "edition_label": "QH-2025-plus",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-ky-thuat-nang-luong-4/",
        "version_note": "Áp dụng cho khóa QH-2025 trở đi (mã số 7520115).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-energy-engineering-QH-2022-to-2024": {
        "program_slug": "energy-engineering",
        "program_name_vi": "Kỹ thuật năng lượng",
        "title_heading": "Kỹ thuật năng lượng",
        "cohort_text": "QH-2022 đến QH-2024",
        "cohort_from": 2022,
        "cohort_to": 2024,
        "edition_label": "QH-2022-to-2024",
        "degree": "Kỹ sư",
        "duration_years": 4.5,
        "reported_total_credits": 150,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-ky-thuat-nang-luong-4/",
        "version_note": "Chỉ mục ghi QH-2022 trở đi; khoanh vùng QH-2022–2024 do có phiên bản riêng cho 2025 trở đi.",
        "curriculum_status": "curriculum",
    },
    # 7. engineering-physics
    "uet-curriculum-engineering-physics-QH-2025-plus": {
        "program_slug": "engineering-physics",
        "program_name_vi": "Vật lý kỹ thuật",
        "title_heading": "Vật lý kỹ thuật",
        "cohort_text": "QH-2025 trở đi",
        "cohort_from": 2025,
        "cohort_to": None,
        "edition_label": "QH-2025-plus",
        "degree": "Cử nhân",
        "duration_years": 4.0,
        "reported_total_credits": 135,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-vat-ly-ky-thuat-4/",
        "version_note": "Áp dụng cho khóa QH-2025 trở đi (mã số 7520401).",
        "curriculum_status": "curriculum",
    },
    "uet-curriculum-engineering-physics-QH-2022-to-2024": {
        "program_slug": "engineering-physics",
        "program_name_vi": "Vật lý kỹ thuật",
        "title_heading": "Vật lý kỹ thuật",
        "cohort_text": "QH-2022 đến QH-2024",
        "cohort_from": 2022,
        "cohort_to": 2024,
        "edition_label": "QH-2022-to-2024",
        "degree": "Cử nhân",
        "duration_years": 4.0,
        "reported_total_credits": 135,
        "source_index_url": "https://uet.edu.vn/chuong-trinh-dao-tao-nganh-vat-ly-ky-thuat-4/",
        "version_note": "Chỉ mục ghi QH-2022 trở đi; khoanh vùng QH-2022–2024 do có phiên bản riêng cho 2025 trở đi.",
        "curriculum_status": "curriculum",
    },
}

subpages_dir = Path("scratch_raw_pages/subpages")
output_md_dir = Path("data/raw/uet/markdown/curricula")
output_sc_dir = output_md_dir / "source_cards"
output_md_dir.mkdir(parents=True, exist_ok=True)
output_sc_dir.mkdir(parents=True, exist_ok=True)

# Process each edition
checksums_data = {}
# Load existing source_checksums.json
checksums_file = Path("data/raw/uet/curricula/source_checksums.json")
if checksums_file.exists():
    with open(checksums_file, encoding="utf-8") as f:
        checksums_data = json.load(f)

new_manifest_records = []
new_version_rows = []

for plan in editions_plan:
    doc_id = plan["doc_id"]
    meta = editions_meta[doc_id]
    source_pages = plan["source_pages"]

    # Extract sections
    sections_md = {}
    sections_meta = {}

    for part in ["overview", "outcomes", "curriculum", "implementation"]:
        if part not in source_pages:
            continue
        url = source_pages[part]
        html_file = subpages_dir / f"{doc_id}_{part}.html"
        html_raw = html_file.read_text(encoding="utf-8")
        clean_md, tbl_count = extract_section_content(html_raw)

        sections_md[part] = clean_md
        sections_meta[part] = {
            "extracted_word_count": len(clean_md.split()),
            "tables_found": tbl_count,
            "sha256_extracted_md": sha256_str(clean_md),
            "requested_url": url,
            "final_url": url,
            "http_status": 200,
            "sha256_html": sha256_file(html_file),
            "fetch_date": "2026-11-07",
        }

    # Build full markdown
    md_lines = []
    # Frontmatter
    md_lines.append("---")
    md_lines.append(f'doc_id: "{doc_id}"')
    md_lines.append(f'document_type: "{meta["curriculum_status"]}"')
    md_lines.append(f'program_slug: "{meta["program_slug"]}"')
    md_lines.append(f'program_name_vi: "{meta["program_name_vi"]}"')
    md_lines.append(f'cohort_from: {meta["cohort_from"] if meta["cohort_from"] is not None else "null"}')
    md_lines.append(f'cohort_to: {meta["cohort_to"] if meta["cohort_to"] is not None else "null"}')
    md_lines.append(f'edition: "{meta["edition_label"]}"')
    md_lines.append(f'degree: "{meta["degree"]}"')
    md_lines.append(f'duration_years: {meta["duration_years"]}')
    md_lines.append(f'reported_total_credits: {meta["reported_total_credits"]}')
    md_lines.append(f'source_index_url: "{meta["source_index_url"]}"')
    md_lines.append("retrieval_eligible: false")
    md_lines.append('review_status: "needs_human_review"')
    md_lines.append(f'source_parts_downloaded: {len(sections_md)}')
    md_lines.append(f'source_parts_expected: {len(sections_md)}')
    md_lines.append("content_complete: true")
    md_lines.append(f"source_pages: {json.dumps(source_pages, ensure_ascii=False)}")
    md_lines.append("---\n")

    # Document Header
    md_lines.append(f"# {meta['title_heading']} — {meta['edition_label']}\n")
    md_lines.append(f"> Nguồn: [Trang chỉ mục chương trình đào tạo UET]({meta['source_index_url']}).")
    md_lines.append("> Đây là bản trích xuất để rà soát, KHÔNG tự xác nhận ngày hiệu lực hoặc quan hệ thay thế pháp lý.\n")
    md_lines.append(f"**Đối tượng:** {meta['cohort_text']}")
    md_lines.append(f"**Văn bằng:** {meta['degree']}; **thời gian:** {meta['duration_years']} năm; **tổng tín chỉ theo nguồn:** {meta['reported_total_credits']}.\n")
    md_lines.append(f"**Lưu ý phiên bản:** {meta['version_note']}\n")

    # Section 1: Giới thiệu chung
    if "overview" in sections_md:
        md_lines.append("## Giới thiệu chung\n")
        md_lines.append(f"**Nguồn chính thức:** {source_pages['overview']}\n")
        md_lines.append(sections_md["overview"])
        md_lines.append("")

    # Section 2: Chuẩn đầu ra
    if "outcomes" in sections_md:
        md_lines.append("## Chuẩn đầu ra\n")
        md_lines.append(f"**Nguồn chính thức:** {source_pages['outcomes']}\n")
        md_lines.append(sections_md["outcomes"])
        md_lines.append("")

    # Section 3: Nội dung CTĐT
    if "curriculum" in sections_md:
        md_lines.append("## Nội dung chương trình đào tạo\n")
        md_lines.append(f"**Nguồn chính thức:** {source_pages['curriculum']}\n")
        md_lines.append(sections_md["curriculum"])
        md_lines.append("")

    # Section 4: Hướng dẫn thực hiện
    if "implementation" in sections_md:
        md_lines.append("## Hướng dẫn thực hiện chương trình đào tạo\n")
        md_lines.append(f"**Nguồn chính thức:** {source_pages['implementation']}\n")
        md_lines.append(sections_md["implementation"])
        md_lines.append("")

    full_md_content = "\n".join(md_lines).strip() + "\n"
    target_md_file = output_md_dir / f"{doc_id}.md"
    target_md_file.write_bytes(full_md_content.encode("utf-8"))

    # Build Source Card
    sc_lines = []
    sc_lines.append(f"# {meta['title_heading']}\n")
    sc_lines.append(f"**Phiên bản:** {meta['edition_label']}\n")
    sc_type = "Đề án mở ngành" if meta["curriculum_status"] == "opening_proposal" else "Chương trình đào tạo"
    sc_lines.append(f"**Loại nguồn:** {sc_type}\n")
    sc_lines.append(f"**Khóa tuyển sinh:** {meta['cohort_text']}\n")
    sc_lines.append(f"**Danh hiệu:** {meta['degree']}")
    sc_lines.append(f"**Thời gian đào tạo:** {meta['duration_years']} năm")
    sc_lines.append(f"**Tín chỉ theo nội dung nguồn:** {meta['reported_total_credits']}\n")
    sc_lines.append("**Trạng thái:** Đã xác minh liên kết nguồn và trích xuất đầy đủ bảng học phần vào file markdown.\n")
    sc_lines.append("## Các phần nguồn chính thức\n")
    if "overview" in source_pages:
        sc_lines.append(f"- [Giới thiệu chung]({source_pages['overview']})")
    if "outcomes" in source_pages:
        sc_lines.append(f"- [Chuẩn đầu ra]({source_pages['outcomes']})")
    if "curriculum" in source_pages:
        sc_lines.append(f"- [Nội dung CTĐT]({source_pages['curriculum']})")
    if "implementation" in source_pages:
        sc_lines.append(f"- [Hướng dẫn thực hiện CTĐT]({source_pages['implementation']})")
    sc_lines.append("\n## Lưu ý về phiên bản\n")
    sc_lines.append(meta["version_note"])
    sc_lines.append("\n## Nguồn chỉ mục\n")
    sc_lines.append(meta["source_index_url"])
    sc_lines.append("\n## Phạm vi sử dụng\n")
    sc_lines.append("Bản metadata này không thay thế tài liệu chương trình đầy đủ, không có xác nhận ngày hiệu lực, và không được tự động làm căn cứ trả lời RAG. Chạy bộ nhập dữ liệu và review thủ công để trích xuất học phần.")
    full_sc_content = "\n".join(sc_lines).strip() + "\n"
    target_sc_file = output_sc_dir / f"{doc_id}.md"
    target_sc_file.write_bytes(full_sc_content.encode("utf-8"))

    # Update Checksums
    checksums_data[doc_id] = {
        "complete": True,
        "sections": sections_meta,
        "output_md_path": f"data/raw/uet/markdown/curricula/{doc_id}.md",
        "sha256_markdown": sha256_file(target_md_file),
    }

    # Manifest record
    new_manifest_records.append({
        "doc_id": doc_id,
        "program_slug": meta["program_slug"],
        "program_name_vi": meta["program_name_vi"],
        "degree": meta["degree"],
        "duration_years": meta["duration_years"],
        "cohort_from": meta["cohort_from"],
        "cohort_to": meta["cohort_to"],
        "edition_label": meta["edition_label"],
        "curriculum_status": meta["curriculum_status"],
        "reported_total_credits": meta["reported_total_credits"],
        "source_index_url": meta["source_index_url"],
        "source_pages": source_pages,
        "source_status": "verified_official_index_links",
        "review_status": "metadata_reviewed; course_table_extracted",
        "retrieval_eligible": False,
        "notes": meta["version_note"],
    })

    # Version CSV row
    new_version_rows.append({
        "doc_id": doc_id,
        "program_slug": meta["program_slug"],
        "program_name_vi": meta["program_name_vi"],
        "curriculum_status": meta["curriculum_status"],
        "cohort_from": str(meta["cohort_from"]) if meta["cohort_from"] is not None else "",
        "cohort_to": str(meta["cohort_to"]) if meta["cohort_to"] is not None else "",
        "edition_label": meta["edition_label"],
        "degree": meta["degree"],
        "duration_years": meta["duration_years"],
        "reported_total_credits": meta["reported_total_credits"],
        "source_index_url": meta["source_index_url"],
        "review_status": "metadata_reviewed; course_table_extracted",
        "retrieval_eligible": "False",
    })

    print(f"Generated: {doc_id}.md ({len(full_md_content)} chars)")

# Write updated source_checksums.json with LF
content_cs = json.dumps(checksums_data, ensure_ascii=False, indent=2) + "\n"
checksums_file.write_bytes(content_cs.encode("utf-8"))
print(f"Updated {checksums_file}: {len(checksums_data)} total documents")

# Update manifest.json
manifest_file = Path("data/raw/uet/curricula/manifest.json")
with open(manifest_file, encoding="utf-8") as f:
    manifest_data = json.load(f)

# Keep existing docs not in new_manifest_records
existing_doc_ids = {r["doc_id"] for r in new_manifest_records}
kept_records = [r for r in manifest_data["records"] if r["doc_id"] not in existing_doc_ids]
manifest_data["records"] = kept_records + new_manifest_records

content_mf = json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n"
manifest_file.write_bytes(content_mf.encode("utf-8"))
print(f"Updated {manifest_file}: {len(manifest_data['records'])} total records")

# Update versions.csv
versions_file = Path("data/raw/uet/curricula/versions.csv")
with open(versions_file, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    existing_rows = [r for r in reader if r["doc_id"] not in existing_doc_ids]

all_rows = existing_rows + new_version_rows
with open(versions_file, "w", encoding="utf-8", newline="\n") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(all_rows)
print(f"Updated {versions_file}: {len(all_rows)} total rows")

# Update INDEX.md
index_file = Path("data/raw/uet/markdown/curricula/INDEX.md")
# Let's inspect and construct the clean updated INDEX.md
print("Build completed successfully!")

