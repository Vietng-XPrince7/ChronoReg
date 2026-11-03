"""Script chính thức chạy sinh dự đoán và đánh giá đối chuẩn RAG (naive_rag vs chrono_rag).

Thực hiện:
1. Nạp tập 90 câu hỏi chuẩn hóa từ data/qa_benchmark/benchmark.jsonl
2. Chạy Naive RAG (baseline không lọc thời gian) và Chrono RAG (định tuyến Zero-Oracle)
3. Lưu kết quả dự đoán ra runs/eval/naive_rag.jsonl và runs/eval/chrono_rag.jsonl
4. Đánh giá toàn diện qua src/eval/evaluator.py và xuất báo cáo runs/eval/comparison_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Thêm root vào sys.path để gọi module src
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Fix mã hóa Unicode trên Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.eval.evaluator import Evaluator
from src.rag.eval_adapter import InMemoryRetriever, RAGEvalAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy sinh dự đoán và đánh giá đối chuẩn RAG")
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("data/qa_benchmark/benchmark.jsonl"),
        help="Đường dẫn file benchmark JSONL",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/eval"),
        help="Thư mục xuất kết quả đánh giá",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Số lượng chunks truy xuất cho mỗi câu hỏi",
    )
    args = parser.parse_args()

    bench_path = args.benchmark
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not bench_path.is_file():
        print(f"[ERROR] Không tìm thấy file benchmark tại {bench_path}")
        return 1

    bench_items = [
        json.loads(line)
        for line in bench_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"[INFO] Nạp {len(bench_items)} câu hỏi benchmark từ {bench_path}")

    # Khởi tạo retriever từ toàn bộ 31 văn bản quy chế đã verified
    retriever = InMemoryRetriever.from_corpus()
    print(f"[INFO] Băm chỉ mục toàn văn BM25 thành công: {len(retriever.chunks)} chunks")

    adapter = RAGEvalAdapter(retriever)

    # 1. Sinh dự đoán Naive RAG
    print("[INFO] Đang chạy dự đoán Naive RAG (baseline)...")
    naive_preds = adapter.run_benchmark(bench_items, mode="naive_rag", top_k=args.top_k)
    naive_file = out_dir / "naive_rag.jsonl"
    RAGEvalAdapter.save_predictions(naive_preds, naive_file)
    print(f"       -> Đã lưu {len(naive_preds)} dự đoán vào {naive_file}")

    # 2. Sinh dự đoán Chrono RAG (Zero-Oracle)
    print("[INFO] Đang chạy dự đoán Chrono RAG (Zero-Oracle Router)...")
    chrono_preds = adapter.run_benchmark(bench_items, mode="chrono_rag", top_k=args.top_k)
    chrono_file = out_dir / "chrono_rag.jsonl"
    RAGEvalAdapter.save_predictions(chrono_preds, chrono_file)
    print(f"       -> Đã lưu {len(chrono_preds)} dự đoán vào {chrono_file}")

    # 3. Đánh giá đối chuẩn qua Evaluator
    evaluator = Evaluator(bench_path)
    comparison = evaluator.compare_systems({
        "naive_rag": naive_preds,
        "chrono_rag": chrono_preds,
    })

    files = evaluator.export_results(comparison, out_dir)
    print(f"\n[SUCCESS] Xuất báo cáo đánh giá hoàn tất:")
    print(f" - Markdown : {files['markdown']}")
    print(f" - CSV      : {files['csv']}")
    print(f" - JSON     : {files['json']}")

    # In kết quả tóm tắt
    print("\n" + "=" * 65)
    print(" KẾT QUẢ ĐỐI CHUẨN HIỆU NĂNG TỔNG THỂ")
    print("=" * 65)
    for sys_name in ["naive_rag", "chrono_rag"]:
        ov = comparison["systems"][sys_name]["overall"]
        print(f"-> {sys_name.upper()}:")
        print(f"   Key-Fact Acc : {ov['key_fact_score']*100:.1f}%")
        print(f"   Token F1     : {ov['token_f1']*100:.1f}%")
        print(f"   Temporal Acc : {ov['temporal_score']*100:.1f}% (Doc: {ov['temporal_doc_accuracy']*100:.1f}%, Year: {ov['temporal_year_accuracy']*100:.1f}%)")
        print(f"   OHR (Lỗi thời): {ov['ohr_rate']*100:.1f}%")
        print(f"   Độ trễ TB    : {ov['latency']['mean_ms']:.1f}ms")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())

