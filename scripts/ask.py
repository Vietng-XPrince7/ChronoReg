"""Script truy vấn kiểm thử quy chế đào tạo UET với ChronoReg.

Hỗ trợ:
- Chrono RAG: Tự động nhận diện mốc thời gian / niên khóa và truy xuất đúng văn bản hiệu lực.
- Naive RAG: Baseline không lọc thời gian để thấy sự khác biệt (thường bị nhầm văn bản cũ).
- Hiển thị đầy đủ bảng dữ liệu, số liệu tài chính, điều khoản quy định từ các chunk liên quan thay vì chỉ trích xuất tiêu đề.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Thêm root vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Fix Unicode terminal trên Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.rag.eval_adapter import InMemoryRetriever, RAGEvalAdapter, _tokenize, extract_relevant_snippet


def format_substantive_answer(chunks: list[dict], question: str, mode_prefix: str) -> str:
    """Định dạng câu trả lời chứa số liệu và nội dung thực tế thay vì chỉ lấy tiêu đề."""
    if not chunks:
        return "Không tìm thấy quy định phù hợp trong hệ thống văn bản."

    q_toks = _tokenize(question)

    # Ưu tiên các chunk có bảng biểu dữ liệu (|---|) hoặc có độ dài đáng kể (> 250 ký tự)
    substantive_chunks = []
    for c in chunks:
        doc = c.get("document", "")
        # Loại bỏ các chunk thuần tiêu đề phụ lục / quốc hiệu
        lines = [l.strip() for l in doc.splitlines() if l.strip()]
        has_content = any(len(l) > 60 or "|" in l or any(char.isdigit() for char in l) for l in lines)
        if has_content and len(doc) > 150:
            substantive_chunks.append(c)

    if not substantive_chunks:
        substantive_chunks = chunks

    # Chọn chunk tốt nhất (chứa bảng biểu hoặc nhiều từ khóa câu hỏi nhất)
    best_chunk = substantive_chunks[0]
    for c in substantive_chunks:
        if "|" in c.get("document", ""):
            best_chunk = c
            break

    doc_text = best_chunk.get("document", "").strip()

    lines = [l.strip() for l in doc_text.splitlines() if l.strip()]

    # Nếu có bảng biểu Markdown, giữ nguyên định dạng bảng để người dùng đọc số liệu
    table_lines = [l for l in lines if "|" in l or l.startswith("#")]
    if len([l for l in table_lines if "|" in l]) >= 2:
        return f"{mode_prefix}\n\n" + "\n".join(table_lines)

    # Nếu không phải bảng, trích xuất đoạn phù hợp nhất từ danh sách dòng
    snippet = extract_relevant_snippet(lines, q_toks, max_len=800, question_raw=question)
    formatted_snippet = "\n\n".join(part.strip() for part in snippet.split(" ; ") if part.strip())
    return f"{mode_prefix}\n\n{formatted_snippet}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Hỏi đáp kiểm thử quy chế đào tạo UET với ChronoReg")
    parser.add_argument("question", type=str, help="Câu hỏi cần tra cứu")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["chrono_rag", "naive_rag"],
        default="chrono_rag",
        help="Chế độ chạy: 'chrono_rag' hoặc 'naive_rag'",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Mốc năm học chỉ định tường minh (tùy chọn)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Số lượng chunks truy xuất (mặc định: 3)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="So sánh trực tiếp cả 2 chế độ Naive RAG và Chrono RAG trên cùng một câu hỏi",
    )

    args = parser.parse_args()

    retriever = InMemoryRetriever.from_corpus()
    adapter = RAGEvalAdapter(retriever)

    print("\n" + "=" * 75)
    print(f"CÂU HỎI: {args.question}")
    print("=" * 75)

    modes = ["chrono_rag", "naive_rag"] if args.compare else [args.mode]

    for m in modes:
        # 1. Chạy đánh giá để lấy routing metadata
        preds = adapter.run_benchmark(
            [{"id": "query", "question": args.question}],
            mode=m,
            top_k=args.top_k,
            as_of_year=args.year,
        )
        res = preds[0]

        tag = "CHRONO RAG (Nhận diện phiên bản/thời gian)" if m == "chrono_rag" else "NAIVE RAG (Truy xuất ngữ nghĩa thuần)"
        print(f"\n--- [{tag}] ---")
        print(f"• Nhóm câu hỏi nhận diện (Inferred Category): {res.get('inferred_category')}")
        print(f"• Mốc năm áp dụng (Target Year): {res.get('as_of_year')}")
        print(f"• Văn bản trích dẫn (Cited Docs): {', '.join(res.get('cited_doc_ids', [])) or 'Không có'}")
        print(f"• Độ trễ xử lý: {res.get('latency_ms')} ms")

        # 2. Truy xuất các chunk thực tế của văn bản được chọn để hiển thị chi tiết số liệu
        cited_doc_ids = res.get("cited_doc_ids", [])
        if cited_doc_ids:
            doc_chunks = [c for c in retriever.chunks if c.get("doc_id") in cited_doc_ids]
        else:
            doc_chunks = []

        prefix = ""
        if m == "chrono_rag":
            cat = res.get("inferred_category")
            target_y = res.get("as_of_year")
            if cat == "active_rule":
                prefix = f"Theo quy định hiện hành mới nhất (áp dụng năm học {target_y}-{target_y+1}):"
            elif cat == "superseded_rule":
                prefix = "Theo quy định cũ trước đây (nay đã được thay thế bởi quy định mới):"
            else:
                prefix = f"Theo quy định áp dụng cho năm học {target_y}-{target_y+1}:"
        else:
            prefix = "Kết quả trích xuất từ văn bản tìm thấy:"

        full_answer = format_substantive_answer(doc_chunks, args.question, prefix)

        print("\nCÂU TRẢ LỜI CHI TIẾT:")
        print(full_answer)
        print("-" * 75)

    return 0


if __name__ == "__main__":
    sys.exit(main())
