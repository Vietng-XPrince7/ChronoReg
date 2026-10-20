"""
src/ingestion/markdown_writer.py
---------------------------------
Tạo file Markdown chuẩn hóa với YAML frontmatter từ DocumentMetadata
và danh sách Section.

Output format (xem docs/schema.md để biết spec đầy đủ):

    ---
    doc_id: "uet-qddt-2023"
    ...
    ---

    # <title>

    ## <Chuong label> — <Chuong title>

    ### <Dieu so> — <Dieu title>

    <!-- meta
    dieu_so: "Điều 15"
    ...
    -->

    <content>
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from src.ingestion.models import ArticleMetadata, DocumentMetadata
from src.ingestion.structure_parser import Section


# ── Helpers ───────────────────────────────────────────────────────────────


def _render_frontmatter(meta: DocumentMetadata) -> str:
    """
    Render YAML frontmatter block.

    Parameters
    ----------
    meta : DocumentMetadata
        Metadata cấp tài liệu.

    Returns
    -------
    str
        Chuỗi ``---\\n<yaml>\\n---``.
    """
    data = meta.to_dict()
    yaml_str = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{yaml_str}---"


def _render_article_meta_comment(article_meta: ArticleMetadata) -> str:
    """
    Render HTML comment chứa metadata cấp Điều.

    Parameters
    ----------
    article_meta : ArticleMetadata
        Metadata cấp Điều/Khoản.

    Returns
    -------
    str
        Chuỗi HTML comment ``<!-- meta\\n...\\n-->``.
    """
    data = {
        "dieu_so": article_meta.dieu_so,
        "khoan_so": article_meta.khoan_so,
        "noi_dung_tom_tat": article_meta.noi_dung_tom_tat,
        "tags": article_meta.tags,
    }
    yaml_str = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"<!-- meta\n{yaml_str}-->"


def _render_section(section: Section) -> str:
    """
    Render một Section thành Markdown.

    Cấu trúc:
    ``### Điều X — <title>``
    ``<!-- meta ... -->``
    ``<content>``

    Parameters
    ----------
    section : Section
        Section cần render.

    Returns
    -------
    str
        Chuỗi Markdown của section.
    """
    heading = f"### {section.dieu_so}"
    if section.dieu_title:
        heading += f" — {section.dieu_title}"

    article_meta = ArticleMetadata(dieu_so=section.dieu_so)
    meta_comment = _render_article_meta_comment(article_meta)

    parts = [heading, "", meta_comment, "", section.content]
    return "\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────


def write_markdown(
    meta: DocumentMetadata,
    sections: list[Section],
    output_dir: Path,
) -> Path:
    """
    Tạo file Markdown chuẩn hóa trong ``output_dir``.

    Tên file: ``{doc_id}.md``.

    Parameters
    ----------
    meta : DocumentMetadata
        Metadata cấp tài liệu.
    sections : list[Section]
        Danh sách Section từ ``structure_parser.parse_sections()``.
    output_dir : Path
        Thư mục đích, thường là ``data/processed/``.

    Returns
    -------
    Path
        Đường dẫn tuyệt đối đến file Markdown vừa tạo.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"{meta.doc_id}.md"

    # ── Build content ──────────────────────────────────────────────────────
    frontmatter = _render_frontmatter(meta)

    doc_heading = f"# {meta.title}"

    # Nhóm sections theo Chương để chèn ## heading
    chuong_rendered: list[str] = []
    last_chuong = ""
    section_blocks: list[str] = []

    for section in sections:
        if section.chuong and section.chuong != last_chuong:
            if section_blocks:
                chuong_rendered.append("\n\n".join(section_blocks))
                section_blocks = []
            chuong_rendered.append(f"\n## {section.chuong}\n")
            last_chuong = section.chuong

        section_blocks.append(_render_section(section))

    if section_blocks:
        chuong_rendered.append("\n\n".join(section_blocks))

    body = "\n\n".join(chuong_rendered)

    full_content = f"{frontmatter}\n\n{doc_heading}\n\n{body}\n"

    out_path.write_text(full_content, encoding="utf-8")
    return out_path

