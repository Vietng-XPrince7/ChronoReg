"""
src/ingestion/pdf_parser.py
---------------------------
Parse PDF → text thô (plain text theo trang), ưu tiên giữ cấu trúc
Chương / Điều / Khoản của văn bản quy phạm pháp luật Việt Nam.

Chiến lược:
  1. Thử pdfplumber trước (layout-aware, giữ được cột/bảng).
  2. Nếu trang trắng hoặc ký tự < MIN_CHARS_PER_PAGE → fallback OCR
     bằng pdf2image + pytesseract (tiếng Việt).

Không phụ thuộc vào bất kỳ thư viện ngoài danh sách requirements.txt.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import pdfplumber

logger = logging.getLogger(__name__)

# Ngưỡng ký tự tối thiểu trên một trang để coi là "có text"
MIN_CHARS_PER_PAGE: int = 50


# ── Helpers ───────────────────────────────────────────────────────────────


def _ocr_page(pdf_path: Path, page_index: int) -> str:
    """
    OCR một trang PDF bằng pdf2image + pytesseract.

    Parameters
    ----------
    pdf_path : Path
        Đường dẫn đến file PDF.
    page_index : int
        Chỉ số trang (bắt đầu từ 0).

    Returns
    -------
    str
        Văn bản OCR của trang đó.
    """
    try:
        from pdf2image import convert_from_path  # noqa: PLC0415
        import pytesseract  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "pdf2image và pytesseract cần được cài để dùng OCR fallback. "
            "Chạy: pip install pdf2image pytesseract"
        ) from exc

    images = convert_from_path(
        str(pdf_path),
        first_page=page_index + 1,
        last_page=page_index + 1,
        dpi=300,
    )
    if not images:
        return ""

    text: str = pytesseract.image_to_string(images[0], lang="vie")
    return text


# ── Public API ────────────────────────────────────────────────────────────


def iter_pages(pdf_path: Path, use_ocr_fallback: bool = True) -> Iterator[str]:
    """
    Yield văn bản của từng trang trong PDF.

    Parameters
    ----------
    pdf_path : Path
        Đường dẫn đến file PDF.
    use_ocr_fallback : bool
        Nếu ``True``, trang ít ký tự sẽ được OCR thay vì bỏ qua.

    Yields
    ------
    str
        Văn bản của mỗi trang (đã strip whitespace thừa ở đầu/cuối).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {pdf_path}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text: str = page.extract_text() or ""
            text = text.strip()

            if len(text) < MIN_CHARS_PER_PAGE:
                if use_ocr_fallback:
                    logger.debug(
                        "Trang %d của '%s' có ít text (%d ký tự), dùng OCR.",
                        i + 1,
                        pdf_path.name,
                        len(text),
                    )
                    text = _ocr_page(pdf_path, i).strip()
                else:
                    logger.debug(
                        "Trang %d của '%s' bị bỏ qua (ít text, OCR tắt).",
                        i + 1,
                        pdf_path.name,
                    )

            yield text


def extract_full_text(pdf_path: Path, use_ocr_fallback: bool = True) -> str:
    """
    Trích xuất toàn bộ nội dung text của một PDF.

    Parameters
    ----------
    pdf_path : Path
        Đường dẫn đến file PDF.
    use_ocr_fallback : bool
        Xem ``iter_pages``.

    Returns
    -------
    str
        Toàn bộ văn bản, các trang cách nhau bằng ``\\n\\n``.
    """
    pages = list(iter_pages(pdf_path, use_ocr_fallback=use_ocr_fallback))
    return "\n\n".join(p for p in pages if p)

