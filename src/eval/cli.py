"""Giao diện dòng lệnh CLI cho module đánh giá (src/eval/cli.py).

Ví dụ chạy:
  python -m src.eval.cli \
      --benchmark data/qa_benchmark/benchmark.jsonl \
      --predictions runs/eval/naive_rag.jsonl:naive_rag runs/eval/chrono_rag.jsonl:chrono_rag \
      --output runs/eval/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .evaluator import Evaluator

# Thiết lập an toàn stdout cho môi trường Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_prediction_arg(arg: str) -> tuple[str, Path]:
    """Phân tích chuỗi đối số <path>[:<system_name>].
    Xử lý an toàn cho đường dẫn Windows có ký tự ổ đĩa (ví dụ C:\\path\\to\\file:system_name).
    """
    arg_str = str(arg).strip()
    if ":" in arg_str:
        parts = arg_str.rsplit(":", 1)
        # Chỉ tách tên hệ thống nếu phần trước không phải là ký tự ổ đĩa đơn (e.g. 'C')
        if len(parts) == 2 and len(parts[0]) > 1:
            return parts[1].strip(), Path(parts[0].strip())
    p = Path(arg_str)
    return p.stem, p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChronoReg Benchmark Evaluator & Comparison CLI")
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("data/qa_benchmark/benchmark.jsonl"),
        help="Đường dẫn đến tệp Benchmark (JSON hoặc JSONL).",
    )
    parser.add_argument(
        "--predictions",
        nargs="+",
        required=True,
        help="Danh sách các tệp dự đoán dạng <path> hoặc <path>:<system_name>.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/eval"),
        help="Thư mục xuất báo cáo và tệp metrics.",
    )

    args = parser.parse_args(argv)

    bench_path = args.benchmark
    if not bench_path.is_file():
        # Fallback thử kiểm tra uet_regulation_benchmark.json
        alt = Path("data/benchmark/uet_regulation_benchmark.json")
        if alt.is_file():
            bench_path = alt
        else:
            print(f"LỖI: Không tìm thấy file Benchmark tại {bench_path}", file=sys.stderr)
            return 1

    evaluator = Evaluator(bench_path)
    systems: dict[str, Path] = {}

    for item in args.predictions:
        name, path = parse_prediction_arg(item)
        if not path.is_file():
            print(f"CẢNH BÁO: Bỏ qua file dự đoán không tồn tại: {path}", file=sys.stderr)
            continue
        systems[name] = path

    if not systems:
        print("LỖI: Không có tệp dự đoán hợp lệ nào để đánh giá.", file=sys.stderr)
        return 1

    comparison = evaluator.compare_systems(systems)
    out_files = evaluator.export_results(comparison, args.output)

    print("\n" + "=" * 65)
    print(" CHRONOREG BENCHMARK EVALUATION COMPLETED")
    print("=" * 65)
    print(f"Benchmark: {bench_path} ({len(evaluator.benchmark)} câu hỏi)")
    print(f"Thư mục xuất: {args.output}\n")

    for sname, sdata in comparison["systems"].items():
        ov = sdata["overall"]
        print(f"-> Hệ thống: {sname}")
        print(f"   Key-Fact Acc : {ov['key_fact_score'] * 100:.1f}%")
        print(f"   Token F1     : {ov['token_f1'] * 100:.1f}%")
        print(f"   Temporal Acc : {ov['temporal_score'] * 100:.1f}%")
        print(f"   OHR (Lỗi thời): {ov['ohr_rate'] * 100:.1f}%")
        print(f"   Độ trễ TB    : {ov['latency']['mean_ms']:.1f}ms\n")

    print(f"Báo cáo Markdown: {out_files['markdown']}")
    print(f"Tệp JSON metrics: {out_files['json']}")
    print(f"Tệp bảng CSV    : {out_files['csv']}")
    print("=" * 65)

    return 0


if __name__ == "__main__":
    sys.exit(main())
