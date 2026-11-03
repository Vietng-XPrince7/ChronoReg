"""Unit tests cho luồng đánh giá tổng thể (src/eval/evaluator.py, cli.py, rag adapter)."""
import json
from pathlib import Path

import pytest
from src.eval.cli import main as cli_main
from src.eval.evaluator import Evaluator
from src.rag.eval_adapter import InMemoryRetriever, RAGEvalAdapter


@pytest.fixture
def mock_benchmark_data():
    return [
        {
            "id": "BENCH_ACT_001",
            "question": "Học phí ngành CNTT năm học 2024-2025 là bao nhiêu?",
            "category": "active_rule",
            "topic": "tuition",
            "target_year": 2024,
            "ground_truth_answer": "Học phí là 1.850.000 đồng/tháng theo Quyết định 4618.",
            "gold_answer": "Học phí là 1.850.000 đồng/tháng theo Quyết định 4618.",
            "source_doc_id": "QD-4618",
            "gold_doc_id": "QD-4618",
            "as_of_year": 2024,
            "key_facts": ["1.850.000 đồng", "QD-4618"],
            "outdated_trap_answer": "980.000 đồng/tháng theo quy định 2021",
        },
        {
            "id": "BENCH_SUP_001",
            "question": "Quy định học phí trước năm 2024 là bao nhiêu?",
            "category": "superseded_rule",
            "topic": "tuition",
            "target_year": 2022,
            "ground_truth_answer": "Mức học phí cũ là 980.000 đồng/tháng.",
            "gold_answer": "Mức học phí cũ là 980.000 đồng/tháng.",
            "source_doc_id": "QD-2022",
            "gold_doc_id": "QD-2022",
            "as_of_year": 2022,
            "key_facts": ["980.000 đồng"],
            "outdated_trap_answer": None,
        },
        {
            "id": "BENCH_TEM_001",
            "question": "Sinh viên khóa 2023 có được xét học bổng KKHT kỳ 1 không?",
            "category": "temporal_specific",
            "topic": "scholarship",
            "target_year": 2023,
            "ground_truth_answer": "Được xét theo kết quả thi tuyển sinh và quy định năm 2023.",
            "gold_answer": "Được xét theo kết quả thi tuyển sinh và quy định năm 2023.",
            "source_doc_id": "QD-HB-2023",
            "gold_doc_id": "QD-HB-2023",
            "as_of_year": 2023,
            "key_facts": ["thi tuyển sinh", "năm 2023"],
            "outdated_trap_answer": "Không được xét kỳ 1",
        },
    ]


@pytest.fixture
def mock_predictions_good():
    return [
        {
            "id": "BENCH_ACT_001",
            "predicted_answer": "Học phí là 1.850.000đ/tháng theo văn bản QD-4618 năm học 2024-2025.",
            "cited_doc_ids": ["QD-4618"],
            "as_of_year": 2024,
            "latency_ms": 25.5,
        },
        {
            "id": "BENCH_SUP_001",
            "predicted_answer": "Mức học phí cũ là 980.000 đồng/tháng theo quyết định QD-2022.",
            "cited_doc_ids": ["QD-2022"],
            "as_of_year": 2022,
            "latency_ms": 18.2,
        },
        {
            "id": "BENCH_TEM_001",
            "predicted_answer": "Được xét dựa vào điểm thi tuyển sinh năm 2023 theo QD-HB-2023.",
            "cited_doc_ids": ["QD-HB-2023"],
            "as_of_year": 2023,
            "latency_ms": 22.0,
        },
    ]


@pytest.fixture
def mock_predictions_outdated():
    return [
        {
            "id": "BENCH_ACT_001",
            # Trả lời bẫy quy chế cũ
            "predicted_answer": "Học phí hiện nay là 980.000 đồng/tháng theo quy định 2021.",
            "cited_doc_ids": ["QD-2021"],
            "as_of_year": 2021,
            "latency_ms": 15.0,
        },
        {
            "id": "BENCH_SUP_001",
            "predicted_answer": "Mức học phí cũ là 980.000 đồng/tháng.",
            "cited_doc_ids": ["QD-2022"],
            "as_of_year": 2022,
            "latency_ms": 16.0,
        },
        {
            "id": "BENCH_TEM_001",
            # Trả lời bẫy
            "predicted_answer": "Không được xét kỳ 1 đối với sinh viên mới.",
            "cited_doc_ids": [],
            "as_of_year": 2023,
            "latency_ms": 14.5,
        },
    ]


def test_evaluator_scoring_and_breakdowns(tmp_path, mock_benchmark_data, mock_predictions_good):
    bench_file = tmp_path / "bench.jsonl"
    with open(bench_file, "w", encoding="utf-8") as f:
        for r in mock_benchmark_data:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    evaluator = Evaluator(bench_file)
    assert len(evaluator.benchmark) == 3

    res = evaluator.evaluate_system("good_system", mock_predictions_good)
    ov = res["overall"]
    assert ov["count"] == 3
    assert ov["key_fact_score"] >= 0.8
    assert ov["temporal_score"] == 1.0
    assert ov["ohr_rate"] == 0.0
    assert ov["latency"]["count"] == 3

    # Phân tách category
    assert "active_rule" in res["by_category"]
    assert "superseded_rule" in res["by_category"]
    assert "temporal_specific" in res["by_category"]

    # Phân tách topic
    assert "tuition" in res["by_topic"]
    assert "scholarship" in res["by_topic"]


def test_compare_systems_and_export_reports(tmp_path, mock_benchmark_data, mock_predictions_good, mock_predictions_outdated):
    bench_file = tmp_path / "bench.json"
    bench_file.write_text(json.dumps(mock_benchmark_data, ensure_ascii=False), encoding="utf-8")

    evaluator = Evaluator(bench_file)
    comparison = evaluator.compare_systems({
        "chrono_rag": mock_predictions_good,
        "naive_rag": mock_predictions_outdated,
    })

    assert len(comparison["systems"]) == 2
    chrono_ov = comparison["systems"]["chrono_rag"]["overall"]
    naive_ov = comparison["systems"]["naive_rag"]["overall"]

    # Chrono RAG phải có điểm cao hơn và OHR thấp hơn Naive RAG
    assert chrono_ov["key_fact_score"] > naive_ov["key_fact_score"]
    assert chrono_ov["ohr_rate"] < naive_ov["ohr_rate"]

    out_dir = tmp_path / "eval_run"
    files = evaluator.export_results(comparison, out_dir)

    assert files["json"].is_file()
    assert files["csv"].is_file()
    assert files["markdown"].is_file()

    # Kiểm tra nội dung markdown
    md_content = files["markdown"].read_text(encoding="utf-8")
    assert "ChronoReg: Báo Cáo Đối Chuẩn Hệ Thống" in md_content
    assert "chrono_rag" in md_content
    assert "naive_rag" in md_content
    assert "active_rule" in md_content


def test_eval_cli_runs_end_to_end(tmp_path, mock_benchmark_data, mock_predictions_good):
    bench_file = tmp_path / "bench.jsonl"
    with open(bench_file, "w", encoding="utf-8") as f:
        for r in mock_benchmark_data:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    pred_file = tmp_path / "predictions.jsonl"
    with open(pred_file, "w", encoding="utf-8") as f:
        for p in mock_predictions_good:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    out_dir = tmp_path / "cli_out"
    exit_code = cli_main([
        "--benchmark", str(bench_file),
        "--predictions", f"{pred_file}:mock_system",
        "--output", str(out_dir),
    ])

    assert exit_code == 0
    assert (out_dir / "summary_metrics.json").is_file()
    assert (out_dir / "comparison_report.md").is_file()


def test_inmemory_retriever_and_rag_adapter(mock_benchmark_data):
    mock_chunks = [
        {
            "chunk_id": "c1",
            "document": "Theo Quyết định 4618 năm học 2024-2025, học phí ngành CNTT là 1.850.000 đồng/tháng.",
            "metadata": {"doc_id": "QD-4618", "start_year": 2024, "academic_year": "2024-2025", "topic_hint": "tuition"},
        },
        {
            "chunk_id": "c2",
            "document": "Quy định năm 2022 mức học phí là 980.000 đồng/tháng.",
            "metadata": {"doc_id": "QD-2022", "start_year": 2022, "academic_year": "2022-2023", "topic_hint": "tuition"},
        },
        {
            "chunk_id": "c3",
            "document": "Năm 2023 sinh viên xét học bổng KKHT dựa trên kết quả thi tuyển sinh.",
            "metadata": {"doc_id": "QD-HB-2023", "start_year": 2023, "academic_year": "2023-2024", "topic_hint": "scholarship"},
        },
    ]

    retriever = InMemoryRetriever(mock_chunks)
    adapter = RAGEvalAdapter(retriever)

    # Chạy chế độ chrono_rag
    preds_chrono = adapter.run_benchmark(mock_benchmark_data, mode="chrono_rag")
    assert len(preds_chrono) == 3
    for p in preds_chrono:
        assert p["mode"] == "chrono_rag"
        assert p["latency_ms"] >= 0.0
        assert "predicted_answer" in p
        assert "cited_doc_ids" in p

    # Câu hỏi 2024 phải truy xuất đúng chunk QD-4618
    p_act = preds_chrono[0]
    assert "QD-4618" in p_act["cited_doc_ids"]

    # Chạy chế độ naive_rag
    preds_naive = adapter.run_benchmark(mock_benchmark_data, mode="naive_rag")
    assert len(preds_naive) == 3
    assert all(p["mode"] == "naive_rag" for p in preds_naive)


def test_chrono_rag_outperforms_naive_rag(tmp_path):
    """Kiểm tra bất biến cốt lõi: Chrono RAG phải vượt trội hơn Naive RAG về Temporal Acc và kiểm soát OHR."""
    benchmark = [
        {
            "id": "BENCH_ACT_001",
            "question": "Học phí ngành CNTT hiện nay là bao nhiêu?",
            "category": "active_rule",
            "topic": "tuition",
            "target_year": 2024,
            "ground_truth_answer": "Học phí là 1.850.000 đồng/tháng theo Quyết định 4618.",
            "gold_answer": "Học phí là 1.850.000 đồng/tháng theo Quyết định 4618.",
            "source_doc_id": "QD-4618",
            "gold_doc_id": "QD-4618",
            "as_of_year": 2024,
            "key_facts": ["1.850.000 đồng", "QD-4618"],
            "outdated_trap_answer": "980.000 đồng/tháng theo QD-2022",
        },
        {
            "id": "BENCH_TEM_001",
            "question": "Học phí ngành CNTT áp dụng cho năm 2022 là bao nhiêu?",
            "category": "temporal_specific",
            "topic": "tuition",
            "target_year": 2022,
            "ground_truth_answer": "Mức học phí năm 2022 là 980.000 đồng/tháng.",
            "gold_answer": "Mức học phí năm 2022 là 980.000 đồng/tháng.",
            "source_doc_id": "QD-2022",
            "gold_doc_id": "QD-2022",
            "as_of_year": 2022,
            "key_facts": ["980.000 đồng"],
            "outdated_trap_answer": "1.850.000 đồng",
        },
    ]

    # Chunk cũ (2022) nhồi từ khóa khiến BM25 không lọc thời gian chọn nhầm
    chunks = [
        {
            "chunk_id": "c1",
            "document": "Theo Quyết định 4618 năm học 2024-2025, học phí ngành CNTT là 1.850.000 đồng/tháng.",
            "metadata": {"doc_id": "QD-4618", "start_year": 2024, "academic_year": "2024-2025", "topic_hint": "tuition"},
        },
        {
            "chunk_id": "c2",
            "document": "Quy định năm 2022 học phí ngành CNTT hiện nay học phí ngành CNTT hiện nay là 980.000 đồng/tháng theo QD-2022.",
            "metadata": {"doc_id": "QD-2022", "start_year": 2022, "academic_year": "2022-2023", "topic_hint": "tuition"},
        },
    ]

    bench_file = tmp_path / "bench.jsonl"
    with open(bench_file, "w", encoding="utf-8") as f:
        for item in benchmark:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    retriever = InMemoryRetriever(chunks)
    adapter = RAGEvalAdapter(retriever)

    preds_naive = adapter.run_benchmark(benchmark, mode="naive_rag")
    preds_chrono = adapter.run_benchmark(benchmark, mode="chrono_rag")

    evaluator = Evaluator(bench_file)
    comparison = evaluator.compare_systems({
        "naive_rag": preds_naive,
        "chrono_rag": preds_chrono,
    })

    naive_ov = comparison["systems"]["naive_rag"]["overall"]
    chrono_ov = comparison["systems"]["chrono_rag"]["overall"]

    # Chrono RAG phải vượt trội về Temporal Accuracy và Key-Fact Accuracy, đồng thời OHR thấp hơn hoặc bằng
    assert chrono_ov["temporal_score"] > naive_ov["temporal_score"]
    assert chrono_ov["key_fact_score"] >= naive_ov["key_fact_score"]
    assert chrono_ov["ohr_rate"] <= naive_ov["ohr_rate"]


