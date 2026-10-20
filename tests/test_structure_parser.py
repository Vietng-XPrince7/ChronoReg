"""
tests/test_structure_parser.py
-------------------------------
Unit tests cho src/ingestion/structure_parser.py.
Chạy: pytest tests/test_structure_parser.py -v
"""

from __future__ import annotations

import pytest

from src.ingestion.structure_parser import parse_sections, _extract_dieu_number


# ── Fixture văn bản mẫu ───────────────────────────────────────────────────

SAMPLE_TEXT = """\
Chương I — QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
Quy chế này quy định về đào tạo trình độ đại học theo hệ thống tín chỉ.

Điều 2. Đối tượng áp dụng
Quy chế này áp dụng cho sinh viên đại học chính quy.

Chương II — TỔ CHỨC ĐÀO TẠO

Điều 3. Chương trình đào tạo
Chương trình đào tạo được xây dựng theo từng ngành học.
1. Khối kiến thức đại cương.
2. Khối kiến thức cơ sở ngành.

Điều 4. Học phần
Học phần là đơn vị kiến thức tối thiểu.
"""


# ── Tests ─────────────────────────────────────────────────────────────────


class TestExtractDieuNumber:
    def test_standard_dot(self):
        dieu_so, title = _extract_dieu_number("Điều 15. Điều kiện xét tốt nghiệp")
        assert dieu_so == "Điều 15"
        assert title == "Điều kiện xét tốt nghiệp"

    def test_standard_colon(self):
        dieu_so, title = _extract_dieu_number("Điều 3: Chương trình đào tạo")
        assert dieu_so == "Điều 3"
        assert "Chương trình" in title

    def test_no_title(self):
        dieu_so, title = _extract_dieu_number("Điều 7")
        assert dieu_so == "Điều 7"
        assert title == ""


class TestParseSections:
    def test_section_count(self):
        sections = parse_sections(SAMPLE_TEXT)
        assert len(sections) == 4, f"Kỳ vọng 4 Điều, nhận được {len(sections)}"

    def test_chuong_assignment(self):
        sections = parse_sections(SAMPLE_TEXT)
        # Điều 1 và 2 thuộc Chương I
        assert "Chương I" in sections[0].chuong
        assert "Chương I" in sections[1].chuong
        # Điều 3 và 4 thuộc Chương II
        assert "Chương II" in sections[2].chuong
        assert "Chương II" in sections[3].chuong

    def test_dieu_so_labels(self):
        sections = parse_sections(SAMPLE_TEXT)
        labels = [s.dieu_so for s in sections]
        assert "Điều 1" in labels
        assert "Điều 4" in labels

    def test_content_not_empty(self):
        sections = parse_sections(SAMPLE_TEXT)
        for s in sections:
            assert s.content.strip(), f"{s.dieu_so} có content rỗng"

    def test_empty_text(self):
        sections = parse_sections("")
        assert sections == []

    def test_text_without_structure(self):
        """Văn bản không có cấu trúc Điều → trả về list rỗng."""
        sections = parse_sections("Đây là văn bản không có Điều nào.")
        assert sections == []

