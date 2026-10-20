"""
src/ingestion/pipeline.py
--------------------------
Entry-point chính của pipeline ingestion.

Sử dụng:
    python -m src.ingestion.pipeline \\
        --input  data/raw/uet/qddt-2023.pdf \\
        --output data/processed/ \\
        --doc-id uet-qddt-2023 \\
        --title  "Quy chế đào tạo UET 2023" \\
        --issuing-body UET \\
        --source-type  quy_che_dao_tao \\
        --effective-date 2023-09-01

Hoặc import trực tiếp:
    from src.ingestion.pipeline import run_ingestion
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.ingestion.models import DocumentMetadata
from src.ingestion.pdf_parser import extract_full_text as pdf_extract
from src.ingestion.docx_parser import extract_full_text as docx_extract
from src.ingestion.structure_parser import parse_sections
from src.ingestion.markdown_writer import write_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Supported file types ──────────────────────────────────────────────────

_EXTRACTORS: dict[str, callable] = {
    ".pdf": lambda p: pdf_extract(p, use_ocr_fallback=True),
    ".docx": docx_extract,
    ".doc": docx_extract,   # python-docx xử lý được nhiều file .doc cũ
    ".md": lambda p: Path(p).read_text(encoding="utf-8"),
    ".txt": lambda p: Path(p).read_text(encoding="utf-8"),
}


# ── Core function ─────────────────────────────────────────────────────────


def run_ingestion(
    input_path: Path,
    output_dir: Path,
    meta: DocumentMetadata,
) -> Path:
    """
    Chạy toàn bộ pipeline: parse → phân tích cấu trúc → ghi Markdown.

    Parameters
    ----------
    input_path : Path
        Đường dẫn đến file gốc (PDF / DOCX / MD / TXT).
    output_dir : Path
        Thư mục đích cho file ``.md`` đầu ra.
    meta : DocumentMetadata
        Metadata do người dùng cung cấp.

    Returns
    -------
    Path
        Đường dẫn đến file Markdown đã tạo trong ``output_dir``.

    Raises
    ------
    ValueError
        Nếu định dạng file không được hỗ trợ.
    FileNotFoundError
        Nếu file đầu vào không tồn tại.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix not in _EXTRACTORS:
        raise ValueError(
            f"Định dạng '{suffix}' chưa được hỗ trợ. "
            f"Các định dạng hỗ trợ: {list(_EXTRACTORS)}"
        )

    logger.info("Bắt đầu xử lý: %s", input_path)

    # ── Bước 1: Trích xuất text thô ───────────────────────────────────────
    extractor = _EXTRACTORS[suffix]
    raw_text: str = extractor(input_path)
    logger.info("Trích xuất text thô: %d ký tự", len(raw_text))

    # ── Bước 2: Phân tích cấu trúc Chương/Điều/Khoản ─────────────────────
    sections = parse_sections(raw_text)
    logger.info("Phát hiện %d Điều/Section", len(sections))

    if not sections:
        logger.warning(
            "Không phát hiện cấu trúc Điều trong '%s'. "
            "Toàn bộ text sẽ được ghi vào một Section duy nhất.",
            input_path.name,
        )
        # Fallback: ghi toàn bộ text như một Section không có số Điều
        from src.ingestion.structure_parser import Section  # noqa: PLC0415
        sections = [
            Section(
                chuong="",
                dieu_so="",
                dieu_title="Nội dung",
                content=raw_text,
            )
        ]

    # ── Bước 3: Ghi Markdown chuẩn hóa ───────────────────────────────────
    out_path = write_markdown(meta, sections, output_dir)
    logger.info("Đã ghi: %s", out_path)

    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ChronoReg ingestion pipeline: PDF/DOCX → Markdown chuẩn hóa."
    )
    p.add_argument("--input", required=True, help="Đường dẫn file đầu vào")
    p.add_argument(
        "--output",
        default="data/processed",
        help="Thư mục đầu ra (mặc định: data/processed)",
    )
    p.add_argument("--doc-id", required=True, help="Khóa chính duy nhất, vd: uet-qddt-2023")
    p.add_argument("--title", required=True, help="Tiêu đề đầy đủ của văn bản")
    p.add_argument(
        "--issuing-body",
        required=True,
        choices=["UET", "VNU", "BGDDT"],
        help="Cơ quan ban hành",
    )
    p.add_argument(
        "--source-type",
        required=True,
        choices=[
            "quy_che_dao_tao",
            "quy_dinh_hoc_phi",
            "thu_tuc_hanh_chinh",
            "thong_bao",
            "quyet_dinh",
        ],
        help="Loại văn bản",
    )
    p.add_argument("--effective-date", required=True, help="Ngày có hiệu lực YYYY-MM-DD")
    p.add_argument("--expired-date", default=None, help="Ngày hết hiệu lực YYYY-MM-DD (tuỳ chọn)")
    p.add_argument("--superseded-by", default=None, help="doc_id văn bản thay thế (tuỳ chọn)")
    p.add_argument(
        "--no-ocr",
        action="store_true",
        help="Tắt OCR fallback cho PDF scan",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    meta = DocumentMetadata(
        doc_id=args.doc_id,
        title=args.title,
        issuing_body=args.issuing_body,
        source_type=args.source_type,
        effective_date=args.effective_date,
        expired_date=args.expired_date,
        superseded_by=args.superseded_by,
        source_file=str(args.input),
    )

    run_ingestion(
        input_path=Path(args.input),
        output_dir=Path(args.output),
        meta=meta,
    )


if __name__ == "__main__":
    main()

