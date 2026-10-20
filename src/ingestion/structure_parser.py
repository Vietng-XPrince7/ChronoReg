"""
src/ingestion/structure_parser.py
----------------------------------
Phân tích cấu trúc logic (Chương / Điều / Khoản / Điểm) từ văn bản
thô của văn bản quy phạm pháp luật Việt Nam.

Đầu vào : Chuỗi plain text (output của pdf_parser / docx_parser).
Đầu ra  : List[Section] — mỗi phần tử đại diện cho một Điều (hoặc
           Khoản nếu muốn chunking mịn hơn).

Các pattern regex được thiết kế cho định dạng chuẩn của văn bản
quy chế Bộ GD&ĐT / ĐHQGHN / UET (tiếng Việt, có dấu).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Regex patterns ────────────────────────────────────────────────────────

# Ví dụ: "Chương I", "Chương II", "Chương 3"
_RE_CHUONG = re.compile(
    r"^(Chương\s+[IVXLCDM\d]+[\.:]?\s*.*)$",
    re.MULTILINE | re.IGNORECASE,
)

# Ví dụ: "Điều 1.", "Điều 15:", "Điều 3 -"
_RE_DIEU = re.compile(
    r"^(Điều\s+\d+[\.:\-]?\s*.*)$",
    re.MULTILINE | re.IGNORECASE,
)

# Ví dụ: "1.", "2." ở đầu dòng (khoản) — phân biệt với số danh sách thường
# Chỉ khớp khi khoản bắt đầu dòng mới sau Điều
_RE_KHOAN = re.compile(
    r"^(\d+\.\s+.+)$",
    re.MULTILINE,
)

# Ví dụ: "a)", "b)", "đ)"
_RE_DIEM = re.compile(
    r"^([a-zđ]\)\s+.+)$",
    re.MULTILINE,
)


# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class Section:
    """
    Đại diện cho một đơn vị nội dung (Điều hoặc Khoản).

    Attributes
    ----------
    chuong : str
        Nhãn chương chứa Điều này, ví dụ ``"Chương IV"``.
    dieu_so : str
        Nhãn Điều, ví dụ ``"Điều 15"``.
    dieu_title : str
        Tiêu đề của Điều (phần sau số Điều).
    khoan_so : Optional[str]
        Nhãn Khoản nếu section này là cấp Khoản, ví dụ ``"Khoản 2"``.
    content : str
        Nội dung đầy đủ của section (bao gồm cả khoản con nếu không tách).
    """

    chuong: str
    dieu_so: str
    dieu_title: str
    content: str
    khoan_so: Optional[str] = None
    sub_sections: list[str] = field(default_factory=list)


# ── Parser ────────────────────────────────────────────────────────────────


def _extract_dieu_number(line: str) -> tuple[str, str]:
    """
    Từ dòng ``"Điều 15. Điều kiện xét tốt nghiệp"`` trả về
    ``("Điều 15", "Điều kiện xét tốt nghiệp")``.
    """
    m = re.match(r"^(Điều\s+\d+)[\.:\-]?\s*(.*)", line, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return line.strip(), ""


def _extract_chuong_label(line: str) -> str:
    """Chuẩn hóa nhãn Chương, ví dụ ``"Chương IV — Thi cử"`` → ``"Chương IV"``."""
    m = re.match(r"^(Chương\s+[IVXLCDM\d]+)", line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return line.strip()


def parse_sections(raw_text: str) -> list[Section]:
    """
    Phân tích văn bản thô thành danh sách các Section (cấp Điều).

    Thuật toán:
    1. Duyệt từng dòng, phát hiện ranh giới Chương → cập nhật
       ``current_chuong``.
    2. Khi gặp dòng ``Điều X``: đóng Section cũ, mở Section mới.
    3. Các dòng còn lại ghép vào ``content`` của Section hiện tại.

    Parameters
    ----------
    raw_text : str
        Văn bản thô từ pdf_parser hoặc docx_parser.

    Returns
    -------
    list[Section]
        Danh sách Section theo thứ tự xuất hiện trong văn bản.
    """
    sections: list[Section] = []
    current_chuong: str = ""
    current_dieu_so: str = ""
    current_dieu_title: str = ""
    current_lines: list[str] = []

    def _flush() -> None:
        """Đóng Section hiện tại và thêm vào danh sách."""
        if current_dieu_so:
            content = "\n".join(current_lines).strip()
            sections.append(
                Section(
                    chuong=current_chuong,
                    dieu_so=current_dieu_so,
                    dieu_title=current_dieu_title,
                    content=content,
                )
            )

    for line in raw_text.splitlines():
        stripped = line.strip()

        # ── Phát hiện Chương ──────────────────────────────────────────
        if _RE_CHUONG.match(stripped):
            current_chuong = _extract_chuong_label(stripped)
            # Không flush: heading Chương thuộc về Điều tiếp theo
            current_lines.append(stripped)
            continue

        # ── Phát hiện Điều ────────────────────────────────────────────
        if _RE_DIEU.match(stripped):
            _flush()
            dieu_so, dieu_title = _extract_dieu_number(stripped)
            current_dieu_so = dieu_so
            current_dieu_title = dieu_title
            current_lines = [stripped]
            continue

        # ── Nội dung thông thường ─────────────────────────────────────
        if stripped:
            current_lines.append(stripped)

    # Flush Section cuối cùng
    _flush()

    return sections

