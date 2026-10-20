"""
src/ingestion/models.py
-----------------------
Pydantic-style dataclass cho DocumentMetadata — nguồn duy nhất
định nghĩa schema metadata của dự án ChronoReg.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocumentMetadata:
    """
    Metadata gắn liền với mỗi tài liệu đã xử lý.

    Attributes
    ----------
    doc_id : str
        Khóa chính duy nhất, ví dụ ``"uet-qddt-2023"``.
    title : str
        Tiêu đề đầy đủ của văn bản.
    issuing_body : str
        Cơ quan ban hành: ``"UET"`` | ``"VNU"`` | ``"BGDDT"``.
    source_type : str
        Loại văn bản: xem ``docs/schema.md`` để biết danh sách hợp lệ.
    effective_date : str
        Ngày có hiệu lực, định dạng ISO 8601 ``"YYYY-MM-DD"``.
    expired_date : Optional[str]
        Ngày hết hiệu lực; ``None`` nếu vẫn còn hiệu lực.
    superseded_by : Optional[str]
        ``doc_id`` của văn bản thay thế; ``None`` nếu chưa bị thay thế.
    source_file : str
        Đường dẫn tương đối đến file gốc trong ``data/raw/``.
    language : str
        Ngôn ngữ tài liệu, mặc định ``"vi"``.
    """

    doc_id: str
    title: str
    issuing_body: str
    source_type: str
    effective_date: str
    source_file: str
    expired_date: Optional[str] = None
    superseded_by: Optional[str] = None
    language: str = "vi"

    def to_dict(self) -> dict:
        """Chuyển sang dict để ghi vào YAML frontmatter."""
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "issuing_body": self.issuing_body,
            "source_type": self.source_type,
            "effective_date": self.effective_date,
            "expired_date": self.expired_date,
            "superseded_by": self.superseded_by,
            "source_file": self.source_file,
            "language": self.language,
        }


@dataclass
class ArticleMetadata:
    """
    Metadata cấp Điều/Khoản, nhúng vào HTML comment trong Markdown output.

    Attributes
    ----------
    dieu_so : str
        Nhãn Điều, ví dụ ``"Điều 15"``.
    khoan_so : Optional[str]
        Nhãn Khoản nếu chunk nhỏ hơn cấp Điều.
    noi_dung_tom_tat : str
        Tóm tắt nội dung 1 câu (dùng làm embedding context).
    tags : list[str]
        Nhãn chủ đề tự do.
    """

    dieu_so: str
    noi_dung_tom_tat: str = ""
    khoan_so: Optional[str] = None
    tags: list[str] = field(default_factory=list)

