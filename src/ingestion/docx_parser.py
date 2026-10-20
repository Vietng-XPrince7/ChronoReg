"""
src/ingestion/docx_parser.py
-----------------------------
Parse DOCX → text thô, giữ cấu trúc Chương / Điều / Khoản.

Chiến lược:
  - Dùng python-docx để đọc paragraph theo thứ tự.
  - Giữ nguyên style heading (Heading 1/2/3) → map sang #/##/###.
  - Bảng (Table) được render thành Markdown table đơn giản.
"""

from __future__ import annotations

import logging
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────


def _table_to_markdown(table: Table) -> str:
    """
    Chuyển một docx.table.Table sang chuỗi Markdown table.

    Parameters
    ----------
    table : Table
        Đối tượng bảng từ python-docx.

    Returns
    -------
    str
        Chuỗi Markdown đại diện cho bảng.
    """
    rows = []
    for i, row in enumerate(table.rows):
        cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
        rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            # Dòng phân cách header
            rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(rows)


def _heading_level(paragraph: Paragraph) -> int | None:
    """
    Trả về cấp heading (1-6) nếu paragraph là heading, ngược lại ``None``.
    """
    style_name: str = paragraph.style.name or ""
    if style_name.startswith("Heading"):
        try:
            return int(style_name.split()[-1])
        except ValueError:
            pass
    return None


# ── Public API ────────────────────────────────────────────────────────────


def extract_full_text(docx_path: Path) -> str:
    """
    Trích xuất toàn bộ nội dung văn bản từ file DOCX.

    Heading → Markdown `#`/`##`/`###`...  
    Bảng → Markdown table.  
    Paragraph thường → văn bản thường.

    Parameters
    ----------
    docx_path : Path
        Đường dẫn đến file .docx.

    Returns
    -------
    str
        Toàn bộ nội dung dưới dạng Markdown thô.
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {docx_path}")

    document = docx.Document(str(docx_path))
    blocks: list[str] = []

    # Duyệt qua body element để giữ đúng thứ tự paragraph + table
    for element in document.element.body:
        tag = element.tag.split("}")[-1]  # lấy tên tag bỏ namespace

        if tag == "p":
            # Paragraph
            para = Paragraph(element, document)
            text = para.text.strip()
            if not text:
                continue

            level = _heading_level(para)
            if level is not None:
                prefix = "#" * min(level, 6)
                blocks.append(f"{prefix} {text}")
            else:
                blocks.append(text)

        elif tag == "tbl":
            # Table
            table = Table(element, document)
            md_table = _table_to_markdown(table)
            if md_table.strip():
                blocks.append(md_table)

        # Các element khác (sectPr, bookmarkStart...) bỏ qua

    return "\n\n".join(blocks)

