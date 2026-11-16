"""Comprehensive accuracy, OOD generalization, and regression test suite for ChronoReg RAG."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.eval.evaluator import Evaluator
from src.eval.metrics import key_fact_score, ohr_score
from src.rag.eval_adapter import (
    RAGEvalAdapter,
    _extract_excluded_phrases,
    _fix_ocr_and_dates,
    _parse_markdown_lines_and_tables,
    detect_topic,
    parse_temporal_intent,
)
from src.rag.pipeline import answer

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = REPO_ROOT / "data/qa_benchmark/benchmark.jsonl"


@pytest.fixture(scope="module")
def rag_adapter() -> RAGEvalAdapter:
    """Load the corpus and BM25 index once for the entire test module."""
    return RAGEvalAdapter()


@pytest.fixture(scope="module")
def benchmark_items() -> list[dict[str, Any]]:
    """Load all 90 benchmark items from disk."""
    if not BENCHMARK_PATH.is_file():
        pytest.skip(f"Benchmark file missing at {BENCHMARK_PATH}")
    return [
        json.loads(line)
        for line in BENCHMARK_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def chrono_eval_results(
    rag_adapter: RAGEvalAdapter,
    benchmark_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run chrono_rag once on the full benchmark and return the Evaluator report."""
    preds = rag_adapter.run_benchmark(benchmark_items, mode="chrono_rag", top_k=4)
    ev = Evaluator(BENCHMARK_PATH)
    report = ev.evaluate_system("chrono_rag", preds)
    report["preds_by_id"] = {p["id"]: p for p in preds}
    report["gold_by_id"] = ev.by_id
    return report


class TestTemporalAndTopicRouting:
    """Verify zero-oracle topic classification and temporal intent extraction."""

    @pytest.mark.parametrize(
        ("question", "expected_topic"),
        [
            ("Mức thu học phí năm học 2026-2027 của khóa QH-2022 là bao nhiêu?", "tuition"),
            ("Học viên cao học kéo dài đóng học phí theo quy định 347/QĐ-KHTC thế nào?", "tuition"),
            ("Quy chế xét cấp học bổng khuyến khích học tập (KKHT) mới nhất của UET?", "scholarship"),
            ("Người học nhận học bổng tài trợ ngoài ngân sách có được nhận KKHT không?", "scholarship"),
            ("Hội nghị sinh viên nghiên cứu khoa học SVNCKH cấp trường tổ chức tháng mấy?", "research"),
            ("Theo kế hoạch học tập 2026-2027, lịch nghỉ Tết Nguyên đán kéo dài mấy tuần?", "academic_calendar"),
            ("Lịch tuần học quân sự GDQPAN của khóa QH-2023 diễn ra vào tuần thứ mấy?", "academic_calendar"),
            ("Theo thời khóa biểu học kỳ I 2022-2023, tiết 1 buổi sáng bắt đầu lúc mấy giờ?", "academic_calendar"),
            ("Đợt bảo vệ khóa luận tốt nghiệp đợt 2 năm 2023 diễn ra vào tuần nào?", "academic_calendar"),
        ],
    )
    def test_detect_topic_routing(self, question: str, expected_topic: str) -> None:
        assert detect_topic(question) == expected_topic

    @pytest.mark.parametrize(
        ("question", "expected_cat", "expected_year"),
        [
            (
                "Sinh viên khóa QH-2022 học lại hoặc cải thiện điểm nộp học phí bao nhiêu một tín chỉ?",
                "active_rule",
                None,
            ),
            (
                "Sinh viên khóa QH-2023 trở về sau khi học bằng kép nộp học phí bao nhiêu hiện nay?",
                "active_rule",
                None,
            ),
            (
                "Trước năm học 2026-2027, mức học phí hệ chuẩn khóa QH-2021 trở về trước trong năm học 2025-2026 là bao nhiêu?",
                "superseded_rule",
                2025,
            ),
            (
                "Trước năm học 2025-2026, mức học phí đại học được quy định như thế nào?",
                "superseded_rule",
                2024,
            ),
            (
                "Quy định phân chia sinh viên nước ngoài đóng 996.000 đ/tín chỉ (trừ Lào và Campuchia) đã bị bãi bỏ bằng nguyên tắc nào?",
                "superseded_rule",
                2025,
            ),
            (
                "Năm học 2022-2023, định mức học phí đào tạo đại học hệ chuẩn đối với khóa tuyển sinh từ 2021 trở về trước là bao nhiêu?",
                "temporal_specific",
                2022,
            ),
            (
                "Quy định về công tác quản lý và sử dụng học bổng tại ĐHQGHN ban hành ngày 07/10/2024 kèm theo quyết định số nào?",
                "temporal_specific",
                2024,
            ),
            (
                "Theo định mức học phí sau đại học 2024–2025, nghiên cứu sinh trúng tuyển trong các năm 2022–2024 đóng bao nhiêu?",
                "temporal_specific",
                2024,
            ),
        ],
    )
    def test_parse_temporal_intent_cases(
        self,
        question: str,
        expected_cat: str,
        expected_year: int | None,
    ) -> None:
        cat, yr = parse_temporal_intent(question)
        assert cat == expected_cat
        assert yr == expected_year


class TestOCRAndTableParsing:
    """Unit tests for OCR text normalization, table row binding, and negative exclusions."""

    def test_fix_ocr_repairs_displaced_decision_stamps_and_dates(self) -> None:
        raw_ocr = (
            "_(Ban hành kèm theo Quyết định số /QĐ-ĐHQGHN, ngày / /2024_ 4618 07 10 "
            "_của Giám đốc Đại học Quốc gia Hà Nội)_\n"
            "Số: /KH-ĐHCN 456 Hà Nội, ngày tháng 05 09 năm 2023\n"
            "Quyết định số: 1931 /QĐ-ĐHCN ngày 07 tháng 8_\n_năm 2026_"
        )
        fixed = _fix_ocr_and_dates(raw_ocr)
        assert "4618/QĐ-ĐHQGHN" in fixed
        assert "07/10/2024" in fixed
        assert "456/KH-ĐHCN" in fixed
        assert "1931/QĐ-ĐHCN" in fixed
        assert "07/08/2026" in fixed

    def test_fix_ocr_cleans_pua_symbols_and_html_breaks(self) -> None:
        raw_calendar = "HỌC KỲ I (28/08/2023 \uf0b8 28/01/2024) | 01/02/2027 -<br>07/02/2027<br>~~a~~"
        fixed = _fix_ocr_and_dates(raw_calendar)
        assert "\uf0b8" not in fixed
        assert "28/08/2023 đến 28/01/2024" in fixed
        assert "01/02–07/02/2027" in fixed
        assert "~~a~~" not in fixed

    def test_extract_excluded_phrases_strips_excluded_majors_only(self) -> None:
        q1 = "Học phí khóa QH-2022 các ngành kỹ thuật (ngoài Nông nghiệp và Hàng không) năm học 2025-2026?"
        clean_q1, excl1 = _extract_excluded_phrases(q1)
        assert "nông nghiệp" not in clean_q1.lower()
        assert "nông" in excl1 or "nông_nghiệp" in excl1
        assert "hàng_không" in excl1 or "hàng" in excl1

        q2 = "Sinh viên nước ngoài đóng học phí 996.000 đ/tín chỉ (trừ Lào và Campuchia) đã bị bãi bỏ thế nào?"
        clean_q2, excl2 = _extract_excluded_phrases(q2)
        assert "lào" in clean_q2.lower()
        assert excl2 == []

    def test_table_parser_preserves_year_vs_month_units_and_scholarship_tiers(self) -> None:
        sample_md = (
            "Điều 3. Định mức học phí các khóa tuyển sinh năm 2024:\n"
            "| Khóa học | Học phí 1 năm học (10 tháng) (đồng) | Học phí 1 tín chỉ (đồng) |\n"
            "|---|---|---|\n"
            "| Khóa QH-2024-I/CQ: Chương trình chuẩn | 32.000.000 | 870.000 |\n"
        )
        lines = _parse_markdown_lines_and_tables(sample_md, doc_id="uet-2024-hoc-phi", topic="tuition")
        joined = "\n".join(lines)
        assert "32.000.000 đồng/năm học" in joined
        assert "870.000 đồng/tín chỉ" in joined
        assert "CLC TT23" not in joined


class TestHardBenchmarkCases:
    """Verify exact facts and document citations on the 29 hardest benchmark questions."""

    @pytest.mark.parametrize(
        "qid",
        [
            "BENCH_ACT_008",
            "BENCH_ACT_009",
            "BENCH_ACT_015",
            "BENCH_ACT_016",
            "BENCH_ACT_017",
            "BENCH_ACT_020",
            "BENCH_ACT_021",
            "BENCH_ACT_023",
            "BENCH_ACT_028",
            "BENCH_ACT_029",
            "BENCH_ACT_030",
            "BENCH_ACT_032",
            "BENCH_ACT_034",
            "BENCH_SUP_001",
            "BENCH_SUP_003",
            "BENCH_SUP_008",
            "BENCH_SUP_010",
            "BENCH_SUP_012",
            "BENCH_SUP_018",
            "BENCH_SUP_019",
            "BENCH_SUP_020",
            "BENCH_SUP_025",
            "BENCH_TEM_001",
            "BENCH_TEM_004",
            "BENCH_TEM_007",
            "BENCH_TEM_014",
            "BENCH_TEM_015",
            "BENCH_TEM_021",
            "BENCH_TEM_026",
        ],
    )
    def test_hard_benchmark_question_achieves_perfect_score(
        self,
        qid: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        details_by_id = {d["id"]: d for d in chrono_eval_results["details"]}
        assert qid in details_by_id
        item_score = details_by_id[qid]
        assert item_score["key_fact_score"] == 1.0
        assert item_score["temporal_doc_correct"] is True
        assert item_score["temporal_year_correct"] is True
        assert item_score["ohr_score"] == 0.0


class TestOutOfDistributionGeneralization:
    """Test natural student questions phrased differently from the benchmark."""

    @pytest.mark.parametrize(
        ("student_query", "expected_doc_id", "expected_year", "expected_facts"),
        [
            (
                "Mình thuộc khóa QH-2022 học lại môn Giải tích hiện nay thì phải đóng học phí bao nhiêu tiền 1 tín chỉ?",
                "uet-2026-quy-dinh-muc-thu-hoc-phi-2026-cdebf4adc3",
                2026,
                ["860.000 đồng/tín chỉ", "QH-2022"],
            ),
            (
                "Cho em hỏi theo Điều 7 quy chế xét học bổng KKHT năm 2026, mỗi học kỳ sinh viên cần hoàn thành tối thiểu mấy tín chỉ?",
                "uet-2026-quy-dinh-xet-hoc-bong-kkht-2026-17a091722e",
                2026,
                ["ít nhất 15 tín chỉ", "Điều 7"],
            ),
            (
                "Theo định mức học phí sau đại học 2024-2025, nghiên cứu sinh trúng tuyển năm 2023 đóng học phí lần đầu và học lại bao nhiêu?",
                "uet-2024-dinh-muc-hoc-phi-sau-dai-hoc-2024-58724ca756",
                2024,
                ["40.000.000 đồng/năm học", "1.218.000 đồng/tín chỉ"],
            ),
            (
                "Tiết 1 buổi sáng theo thời khóa biểu học kỳ I 2022-2023 của UET bắt đầu và kết thúc lúc mấy giờ?",
                "uet-thoi-khoa-bieu-hoc-ki-i-2022-2023-d5f2256636",
                2022,
                ["07h00", "07h50", "tiết 1"],
            ),
            (
                "Theo quyết định số 347/QĐ-KHTC, nghiên cứu sinh trong thời gian đào tạo kéo dài tính mức thu học phí như thế nào?",
                "uet-2022-dinh-muc-hoc-phi-dao-tao-sau-dai-hoc-trong-thoi-gian-keo-da-99fea0261a",
                2022,
                ["50% mức học phí năm học", "347/QĐ-KHTC"],
            ),
        ],
    )
    def test_paraphrased_queries_generalize_accurately(
        self,
        student_query: str,
        expected_doc_id: str,
        expected_year: int,
        expected_facts: list[str],
    ) -> None:
        out = answer(student_query, mode="chrono_rag")
        assert out["as_of_year"] == expected_year
        assert expected_doc_id in out["cited_doc_ids"]
        assert key_fact_score(out["predicted_answer"], expected_facts) == 1.0


class TestOutdatedHallucinationDefense:
    """Verify OHR detection logic and ensure ChronoRAG never emits unflagged outdated traps."""

    def test_ohr_metric_flags_unwarned_outdated_numbers_and_years(self) -> None:
        assert ohr_score(
            predicted="Mức học phí hiện hành là 1.850.000 đồng/tháng.",
            outdated_trap_answer="1.850.000 đồng/tháng (mức năm 2025-2026)",
            category="active_rule",
            target_year=2026,
            predicted_year=2026,
        ) == 1.0

        assert ohr_score(
            predicted="Mức học phí áp dụng là 3.000.000 đồng/tháng.",
            outdated_trap_answer=None,
            category="active_rule",
            target_year=2026,
            predicted_year=2025,
        ) == 1.0

        assert ohr_score(
            predicted="Theo quy định cũ trước đây năm học 2025-2026 (đã bị thay thế): 1.850.000 đồng/tháng, nay thay bằng 2.090.000 đồng/tháng.",
            outdated_trap_answer="1.850.000 đồng/tháng",
            category="superseded_rule",
            target_year=2025,
            predicted_year=2025,
        ) == 0.0

    def test_zero_ohr_across_all_active_and_superseded_benchmark_questions(
        self,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        violating = [d["id"] for d in chrono_eval_results["details"] if d["ohr_score"] > 0.0]
        assert violating == []


class TestFullBenchmarkRegressionGate:
    """Lock 100% accuracy across every category, topic, and academic year slice."""

    def test_overall_100_percent_accuracy(self, chrono_eval_results: dict[str, Any]) -> None:
        ov = chrono_eval_results["overall"]
        assert ov["count"] == 90
        assert ov["key_fact_score"] == 1.0
        assert ov["temporal_doc_accuracy"] == 1.0
        assert ov["temporal_year_accuracy"] == 1.0
        assert ov["temporal_score"] == 1.0
        assert ov["ohr_rate"] == 0.0
        assert ov["token_f1"] >= 0.35

    @pytest.mark.parametrize("category", ["active_rule", "superseded_rule", "temporal_specific"])
    def test_100_percent_accuracy_per_category(
        self,
        category: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        cat_metrics = chrono_eval_results["by_category"][category]
        assert cat_metrics["key_fact_score"] == 1.0
        assert cat_metrics["temporal_score"] == 1.0
        assert cat_metrics["ohr_rate"] == 0.0

    @pytest.mark.parametrize("topic", ["hoc_phi", "hoc_bong", "nckh", "dao_tao"])
    def test_100_percent_accuracy_per_topic(
        self,
        topic: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        topic_metrics = chrono_eval_results["by_topic"][topic]
        assert topic_metrics["key_fact_score"] == 1.0
        assert topic_metrics["temporal_score"] == 1.0
        assert topic_metrics["ohr_rate"] == 0.0

    @pytest.mark.parametrize("year", ["2022", "2023", "2024", "2025", "2026"])
    def test_100_percent_accuracy_per_target_year(
        self,
        year: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        year_metrics = chrono_eval_results["by_year"][year]
        assert year_metrics["key_fact_score"] == 1.0
        assert year_metrics["temporal_score"] == 1.0
        assert year_metrics["ohr_rate"] == 0.0

