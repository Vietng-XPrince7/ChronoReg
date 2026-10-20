"""
tests/test_markdown_writer.py
-------------------------------
Unit tests cho src/ingestion/markdown_writer.py.
Chạy: pytest tests/test_markdown_writer.py -v
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import yaml

from src.ingestion.markdown_writer import write_markdown
from src.ingestion.models import DocumentMetadata
from src.ingestion.structure_parser import Section


# ── Fixtures ──────────────────────────────────────────────────────────────

META = DocumentMetadata(
    doc_id="test-doc-2023",
    title="Quy chế thử nghiệm 2023",
    issuing_body="UET",
    source_type="quy_che_dao_tao",
    effective_date="2023-09-01",
    source_file="data/raw/uet/test.pdf",
)

SECTIONS = [
    Section(
        chuong="Chương I",
        dieu_so="Điều 1",
        dieu_title="Phạm vi điều chỉnh",
        content="Quy chế này quy định...",
    ),
    Section(
        chuong="Chương I",
        dieu_so="Điều 2",
        dieu_title="Đối tượng áp dụng",
        content="Áp dụng cho sinh viên...",
    ),
]


# ── Tests ─────────────────────────────────────────────────────────────────


class TestWriteMarkdown:
    def test_file_created(self, tmp_path):
        out = write_markdown(META, SECTIONS, tmp_path)
        assert out.exists(), "File output không được tạo"
        assert out.name == f"{META.doc_id}.md"

    def test_frontmatter_present(self, tmp_path):
        out = write_markdown(META, SECTIONS, tmp_path)
        content = out.read_text(encoding="utf-8")
        assert content.startswith("---"), "Thiếu YAML frontmatter"

    def test_frontmatter_parseable(self, tmp_path):
        out = write_markdown(META, SECTIONS, tmp_path)
        content = out.read_text(encoding="utf-8")
        # Extract YAML block between first two ---
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        assert fm_match, "Không parse được frontmatter"
        data = yaml.safe_load(fm_match.group(1))
        assert data["doc_id"] == META.doc_id
        assert data["issuing_body"] == META.issuing_body
        assert data["effective_date"] == META.effective_date

    def test_dieu_headings(self, tmp_path):
        out = write_markdown(META, SECTIONS, tmp_path)
        content = out.read_text(encoding="utf-8")
        assert "### Điều 1" in content
        assert "### Điều 2" in content

    def test_chuong_heading(self, tmp_path):
        out = write_markdown(META, SECTIONS, tmp_path)
        content = out.read_text(encoding="utf-8")
        assert "## Chương I" in content

    def test_meta_comment_present(self, tmp_path):
        out = write_markdown(META, SECTIONS, tmp_path)
        content = out.read_text(encoding="utf-8")
        assert "<!-- meta" in content

    def test_empty_sections(self, tmp_path):
        """File vẫn được tạo khi không có section nào."""
        out = write_markdown(META, [], tmp_path)
        assert out.exists()

