"""Automated unit and benchmark regression tests for ChronoReg RAG (tests/test_rag_accuracy.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval.evaluator import Evaluator
from src.rag.eval_adapter import RAGEvalAdapter, detect_topic, parse_temporal_intent
from src.rag.pipeline import answer

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = REPO_ROOT / "data/qa_benchmark/benchmark.jsonl"


@pytest.fixture(scope="module")
def rag_adapter() -> RAGEvalAdapter:
    """Shared RAGEvalAdapter instance loaded once per test module."""
    return RAGEvalAdapter()


class TestTemporalAndTopicRouting:
    """Unit tests for zero-oracle topic detection and temporal intent parsing."""

    def test_detect_topic_categories(self) -> None:
        assert detect_topic("Mức thu học phí năm học 2026-2027 là bao nhiêu?") == "tuition"
        assert detect_topic("Quy chế xét học bổng KKHT mới nhất của UET?") == "scholarship"
        assert detect_topic("Hội nghị sinh viên nghiên cứu khoa học SVNCKH tổ chức tháng mấy?") == "research"
        assert detect_topic("Kế hoạch học tập năm học 2026-2027 nghỉ Tết Nguyên đán mấy tuần?") == "academic_calendar"
        assert detect_topic("Theo thời khóa biểu học kỳ I 2022-2023, tiết 1 bắt đầu mấy giờ?") == "academic_calendar"

    def test_parse_temporal_intent_distinguishes_cohort_from_academic_year(self) -> None:
        # Cohort QH-2022 without academic year -> active_rule
        cat, yr = parse_temporal_intent(
            "Sinh viên khóa QH-2022 học lại hoặc học cải thiện điểm nộp học phí bao nhiêu tiền một tín chỉ?"
        )
        assert cat == "active_rule"
        assert yr is None

    def test_parse_temporal_intent_superseded_and_prior_year(self) -> None:
        cat, yr = parse_temporal_intent(
            "Trước năm học 2026-2027, mức học phí hệ chuẩn khóa QH-2021 trở về trước trong năm học 2025-2026 là bao nhiêu?"
        )
        assert cat == "superseded_rule"
        assert yr == 2025

    def test_parse_temporal_intent_abolished_foreign_student_rule(self) -> None:
        cat, yr = parse_temporal_intent(
            "Quy định phân chia sinh viên nước ngoài đóng học phí 996.000 đ/tín chỉ (trừ Lào và Campuchia) đã bị bãi bỏ bằng nguyên tắc nào?"
        )
        assert cat == "superseded_rule"
        assert yr == 2025

    def test_parse_temporal_intent_temporal_specific(self) -> None:
        cat, yr = parse_temporal_intent(
            "Năm học 2022-2023, định mức học phí đào tạo đại học hệ chuẩn khóa tuyển sinh từ 2021 trở về trước là bao nhiêu?"
        )
        assert cat == "temporal_specific"
        assert yr == 2022


class TestPipelineContract:
    """Verify src/rag/pipeline.py output schema and runtime behavior."""

    def test_pipeline_answer_contract_chrono_rag(self) -> None:
        res = answer(
            "Theo kế hoạch học tập bậc đại học năm học 2026–2027, lịch nghỉ Tết Nguyên đán được bố trí trong bao nhiêu tuần và từ ngày nào đến ngày nào?",
            mode="chrono_rag",
        )
        assert isinstance(res, dict)
        for key in ("answer", "predicted_answer", "prediction", "as_of_year", "sources", "cited_doc_ids", "mode", "debug"):
            assert key in res
        assert res["mode"] == "chrono_rag"
        assert res["as_of_year"] == 2026
        assert "01/02–07/02/2027" in res["answer"]
        assert "08/02–14/02/2027" in res["answer"]
        assert "uet-2026-ke-hoach-hoc-tap-2026-413e3e36cd" in res["cited_doc_ids"]

    def test_pipeline_rejects_empty_question(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            answer("   ")


@pytest.mark.skipif(not BENCHMARK_PATH.is_file(), reason="Benchmark file not found")
class TestFullBenchmarkRegressionGate:
    """End-to-end regression gate locking 100% accuracy on the 90-question UET benchmark."""

    def test_chrono_rag_achieves_100_percent_accuracy_and_zero_ohr(self, rag_adapter: RAGEvalAdapter) -> None:
        items = [
            json.loads(line)
            for line in BENCHMARK_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(items) == 90

        chrono_preds = rag_adapter.run_benchmark(items, mode="chrono_rag", top_k=4)
        naive_preds = rag_adapter.run_benchmark(items, mode="naive_rag", top_k=4)

        ev = Evaluator(BENCHMARK_PATH)
        chrono_eval = ev.evaluate_system("chrono_rag", chrono_preds)
        naive_eval = ev.evaluate_system("naive_rag", naive_preds)

        ov_chrono = chrono_eval["overall"]
        ov_naive = naive_eval["overall"]

        # 1. Lock in 100% Key-Fact Accuracy, 100% Temporal Accuracy, and 0.0% OHR
        assert ov_chrono["key_fact_score"] == 1.0, (
            f"Expected 100% Key-Fact Acc, got {ov_chrono['key_fact_score']*100:.2f}%"
        )
        assert ov_chrono["temporal_doc_accuracy"] == 1.0, (
            f"Expected 100% Temporal Doc Acc, got {ov_chrono['temporal_doc_accuracy']*100:.2f}%"
        )
        assert ov_chrono["temporal_year_accuracy"] == 1.0, (
            f"Expected 100% Temporal Year Acc, got {ov_chrono['temporal_year_accuracy']*100:.2f}%"
        )
        assert ov_chrono["temporal_score"] == 1.0
        assert ov_chrono["ohr_rate"] == 0.0, (
            f"Expected 0.0% OHR, got {ov_chrono['ohr_rate']*100:.2f}%"
        )

        # 2. Verify Chrono RAG strictly outperforms Naive RAG across all key dimensions
        assert ov_chrono["key_fact_score"] > ov_naive["key_fact_score"]
        assert ov_chrono["temporal_score"] > ov_naive["temporal_score"]
        assert ov_chrono["ohr_rate"] < ov_naive["ohr_rate"]
        assert ov_chrono["token_f1"] > ov_naive["token_f1"]