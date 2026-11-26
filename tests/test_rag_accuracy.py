"""Comprehensive accuracy, OOD generalization, and regression test suite for ChronoReg RAG."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.eval.evaluator import Evaluator
from src.eval.metrics import key_fact_score, normalize_vietnamese, ohr_score, temporal_accuracy
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


# ==============================================================================
# 1. TEMPORAL & TOPIC ROUTING UNIT TESTS
# ==============================================================================
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
            # Cohort years (QH-2021, QH-2022, K67-K70) without academic year -> active_rule
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
            # Superseded rules with explicit comparison or "trước năm học"
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
                None,
            ),
            # Temporal specific with academic year range, single year, or promulgation date
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


# ==============================================================================
# 2. OCR REPAIR, TABLE PARSING & EXCLUSION EXTRACTION TESTS
# ==============================================================================
class TestOCRAndTableParsing:
    """Unit tests for OCR text normalization, table row binding, and negative exclusions."""

    def test_fix_ocr_repairs_displaced_decision_stamps_and_dates(self) -> None:
        raw_ocr = (
            "_(Ban hành kèm theo Quyết định số /QĐ-ĐHQGHN, ngày / /2024_ 4618 07 10 "
            "_của Giám đốc Đại học Quốc gia Hà Nội)_\n"
            "Số: /KH-ĐHCN 456 Hà Nội, ngày tháng 05 09 năm 2023\n"
            "Quyết định số: 1931 /QĐ-ĐHCN ngày 07 tháng 8\n_năm 2026_"
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

        # Must NOT strip "(trừ Lào và Campuchia)" because it is part of the target rule description
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


# ==============================================================================
# 3. HARD BENCHMARK CASES REGRESSION TESTS
# ==============================================================================
class TestHardBenchmarkCases:
    """Verify exact facts and document citations on the 24 hardest benchmark questions."""

    @pytest.mark.parametrize(
        "qid",
        [
            "BENCH_ACT_008",  # QH-2022 retake tuition (undergrad vs postgrad disambiguation)
            "BENCH_ACT_009",  # QH-2023+ dual degree / retake tuition
            "BENCH_ACT_015",  # Active doc referencing 347/QĐ-KHTC extended training
            "BENCH_ACT_016",  # 1931/QĐ-ĐHCN promulgation & effective date
            "BENCH_ACT_017",  # Điều 7 minimum 15 credits & final semester rule
            "BENCH_ACT_020",  # 4618/QĐ-ĐHQGHN OCR stamp recovery
            "BENCH_ACT_021",  # Simultaneous KKHT & non-budget sponsored scholarship
            "BENCH_ACT_023",  # SVNCKH 2025-2026 school-level May 2026 & faculty April 2026
            "BENCH_ACT_028",  # 4 graduation periods (Sep, Dec, Mar, Jun)
            "BENCH_ACT_029",  # Other VNU unit dual-degree tuition across all 3 cohorts
            "BENCH_ACT_030",  # 2025-2026 KKHT Xuất sắc rate for QH-2022 remaining majors
            "BENCH_ACT_032",  # Comparative QH-2022 CNNN (2.150.000) vs remaining majors (3.200.000)
            "BENCH_ACT_034",  # 2026-2027 Lunar New Year 2 weeks (01/02-07/02 & 08/02-14/02/2027)
            "BENCH_SUP_001",  # Dual-version 2025-2026 vs 2026-2027 for QH-2021
            "BENCH_SUP_003",  # Excluded majors "(ngoài Nông nghiệp và Hàng không)" dual-version
            "BENCH_SUP_008",  # 2024-2025 QH-2024 CNTT/AI (32.000.000/năm & 870.000/tín chỉ)
            "BENCH_SUP_010",  # 2024-2025 PhD (36.000.000 & 1.091.000) vs Master disambiguation
            "BENCH_SUP_012",  # Abolished 996.000 foreign student rule -> equal to Vietnamese students
            "BENCH_SUP_018",  # 2024-2025 Viện TTNT NCKH dates (27/02/2025 & 06-15/03/2025)
            "BENCH_SUP_019",  # 347/QĐ-KHTC PhD extended tuition (50%)
            "BENCH_SUP_020",  # 347/QĐ-KHTC Master extended tuition (actual registered credits)
            "BENCH_SUP_025",  # 2023-2024 KLTN đợt 2 week 15 (04/12/2023-10/12/2023)
            "BENCH_TEM_001",  # 2022-2023 QH-2021 standard tuition (all 3 units: month, year, credit)
            "BENCH_TEM_004",  # 2022-2023 CLC TT23 QH-2019..2021 retake (800.000 đ/tín chỉ)
            "BENCH_TEM_007",  # 2024-2025 QH-2022 CNNN nhóm 3 (18.700.000/năm & 510.000/tín chỉ)
            "BENCH_TEM_014",  # 2023-2024 Semester II start/end dates (29/01/2024 - 30/06/2024)
            "BENCH_TEM_015",  # 2023-2024 Faculty NCKH week 29 (11/03/2024 - 17/03/2024)
            "BENCH_TEM_021",  # 2022-2023 Timetable period 1 (07h00 - 07h50)
            "BENCH_TEM_026",  # 1931/QĐ-ĐHCN target audience (regular undergrad in standard time)
        ],
    )
    def test_hard_benchmark_question_achieves_perfect_score(
        self,
        qid: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        details_by_id = {d["id"]: d for d in chrono_eval_results["details"]}
        assert qid in details_by_id, f"Question ID {qid} not found in benchmark"
        item_score = details_by_id[qid]
        pred = chrono_eval_results["preds_by_id"][qid]
        gold = chrono_eval_results["gold_by_id"][qid]

        assert item_score["key_fact_score"] == 1.0, (
            f"[{qid}] Key-Fact Score={item_score['key_fact_score']} < 1.0\n"
            f"  Key Facts: {gold.get('key_facts')}\n"
            f"  Pred Ans : {pred['predicted_answer']}"
        )
        assert item_score["temporal_doc_correct"] is True, (
            f"[{qid}] Wrong document cited: {pred.get('cited_doc_ids')} vs gold {gold.get('source_doc_id')}"
        )
        assert item_score["temporal_year_correct"] is True, (
            f"[{qid}] Wrong year: {pred.get('as_of_year')} vs gold {gold.get('target_year')}"
        )
        assert item_score["ohr_score"] == 0.0, f"[{qid}] Triggered OHR hallucination!"


# ==============================================================================
# 4. OUT-OF-DISTRIBUTION (PARAPHRASED STUDENT QUERIES) GENERALIZATION TESTS
# ==============================================================================
class TestOutOfDistributionGeneralization:
    """Test natural student questions phrased differently from the benchmark."""

    @pytest.mark.parametrize(
        ("student_query", "expected_doc_id", "expected_year", "expected_facts"),
        [
            (
                "Mình thuộc khóa QH-2022 học lại môn Giải tích hiện nay thì phải đóng bao nhiêu tiền 1 tín chỉ?",
                "uet-2026-quy-dinh-muc-thu-hoc-phi-2026-cdebf4adc3",
                2026,
                ["860.000 đồng/tín chỉ", "QH-2022"],
            ),
            (
                "Cho em hỏi theo Điều 7 quy chế học bổng KKHT năm 2026, mỗi học kỳ sinh viên cần tích lũy tối thiểu mấy tín chỉ để được xét?",
                "uet-2026-quy-dinh-xet-hoc-bong-kkht-2026-17a091722e",
                2026,
                ["ít nhất 15 tín chỉ", "Điều 7"],
            ),
            (
                "Nghiên cứu sinh tiến sĩ khóa QH-2023 trong năm học 2024-2025 đóng học phí lần đầu 1 năm là bao nhiêu?",
                "uet-2024-dinh-muc-hoc-phi-sau-dai-hoc-2024-58724ca756",
                2024,
                ["40.000.000 đồng/năm học", "1.218.000 đồng/tín chỉ"],
            ),
            (
                "Tiết 1 buổi sáng theo thời khóa biểu học kỳ 1 năm học 2022-2023 bắt đầu từ mấy giờ đến mấy giờ?",
                "uet-thoi-khoa-bieu-hoc-ki-i-2022-2023-d5f2256636",
                2022,
                ["07h00", "07h50", "tiết 1"],
            ),
            (
                "Theo quyết định 347/QĐ-KHTC, nghiên cứu sinh bị kéo dài thời gian đào tạo thì tính học phí như thế nào?",
                "uet-2022-dinh-muc-hoc-phi-dao-tao-sau-dai-hoc-trong-thoi-gian-keo-da-99fea0261a",
                2022,
                ["50% mức học phí năm học", "347/QĐ-KHTC"],
            ),
            (
                "Tiết 2 buổi sáng bắt đầu lúc mấy giờ?",
                "uet-thoi-khoa-bieu-hoc-ki-i-2022-2023-d5f2256636",
                2022,
                ["08h00", "08h50", "tiết 2"],
            ),
            (
                "Tiết 7 buổi chiều học từ mấy giờ đến mấy giờ?",
                "uet-thoi-khoa-bieu-hoc-ki-i-2022-2023-d5f2256636",
                2022,
                ["13h00", "13h50", "tiết 7"],
            ),
            (
                "Chậm nộp học phí có bị cấm thi không?",
                "uet-quy-dinh-nop-hoc-phi-2021-f480728f8f",
                2021,
                ["cấm thi", "hạ một bậc điểm rèn luyện"],
            ),
            (
                "Ngành Công nghệ thông tin có những môn học nào?",
                "uet-ctdt-cong-nghe-thong-tin-tkb",
                2022,
                ["Công nghệ thông tin"],
            ),
            (
                "Ngành Khoa học dữ liệu gồm bao nhiêu tín chỉ?",
                "uet-curriculum-data-science-QH-2025-plus",
                2025,
                ["135 tín chỉ", "Khoa học dữ liệu"],
            ),
            (
                "Quy định học phí đào tạo tiến sĩ mới nhất hiện nay là bao nhiêu?",
                "uet-2026-quy-dinh-muc-thu-hoc-phi-2026-cdebf4adc3",
                2026,
                ["4.500.000", "1.375.000"],
            ),
            (
                "Môn Cở sở dữ liệu có bao nhiêu tín chỉ ?",
                "uet-ctdt-mang-may-tinh-va-truyen-thong-du-lieu-tkb",
                2022,
                ["Cơ sở dữ liệu", "INT2211", "4"],
            ),
            (
                "Học phần INT2210 bao nhiêu tín chỉ?",
                "uet-ctdt-he-thong-thong-tin-tkb",
                2022,
                ["INT2210", "4"],
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

    @pytest.mark.parametrize(
        ("course_query", "expected_facts"),
        [
            ("Môn Cơ sở dữ liệu có bao nhiêu tín chỉ?", ["Cơ sở dữ liệu", "INT2211", "4"]),
            ("Học phần INT2210 bao nhiêu tín chỉ?", ["INT2210", "4"]),
            ("Môn Lập trình hướng đối tượng có mấy tín chỉ?", ["Lập trình hướng đối tượng", "INT2204", "3"]),
        ],
    )
    def test_course_queries_omit_redundant_major_prefix(
        self,
        course_query: str,
        expected_facts: list[str],
    ) -> None:
        out = answer(course_query, mode="chrono_rag")
        assert "Học phần ngành " not in out["predicted_answer"]
        assert key_fact_score(out["predicted_answer"], expected_facts) == 1.0

    @pytest.mark.parametrize(
        ("summer_query", "expected_doc_id", "expected_year", "expected_facts"),
        [
            (
                "Học kỳ phụ năm học 2026-2027 diễn ra từ ngày nào đến ngày nào?",
                "uet-2026-ke-hoach-hoc-tap-2026-413e3e36cd",
                2026,
                ["05/07/2027", "29/08/2027"],
            ),
            (
                "Học kỳ phụ năm học 2025-2026 diễn ra từ ngày nào đến ngày nào?",
                "uet-2025-ke-hoach-hoc-tap-2025-1372cdf5f4",
                2025,
                ["06/07/2026", "31/08/2026"],
            ),
            (
                "Học kỳ phụ năm học 2024-2025 diễn ra từ ngày nào đến ngày nào?",
                "uet-2024-ke-hoach-hoc-tap-2024-ad259a29a6",
                2024,
                ["07/07/2025", "31/08/2025"],
            ),
            (
                "Học kỳ phụ năm học 2023-2024 diễn ra từ ngày nào đến ngày nào?",
                "uet-2023-ke-hoach-hoc-tap-2023-3ad1bf476e",
                2023,
                ["01/07/2024", "18/08/2024"],
            ),
        ],
    )
    def test_summer_term_date_ranges(
        self,
        summer_query: str,
        expected_doc_id: str,
        expected_year: int,
        expected_facts: list[str],
    ) -> None:
        out = answer(summer_query, mode="chrono_rag")
        assert out["as_of_year"] == expected_year
        assert expected_doc_id in out["cited_doc_ids"]
        assert key_fact_score(out["predicted_answer"], expected_facts) == 1.0

    @pytest.mark.parametrize(
        ("course_query", "expected_facts"),
        [
            ("Học phần MAT1041 Giải tích 1 có mấy tín chỉ?", ["Giải tích 1", "MAT1041", "4"]),
            ("Môn Giải tích 1 có bao nhiêu tín chỉ?", ["MAT1041", "4", "UET.MAT1050", "5"]),
            ("Môn Đại số có mấy tín chỉ?", ["Đại số", "MAT1093", "4"]),
            ("Môn Trí tuệ nhân tạo có mấy tín chỉ?", ["Trí tuệ nhân tạo", "INT3401", "3"]),
            ("Môn Mạng máy tính có bao nhiêu tín chỉ?", ["UET.CN2042", "3", "INT2213", "4"]),
            ("Môn Mạng máy tính khóa QH-2025 có bao nhiêu tín chỉ?", ["UET.CN2042", "3"]),
        ],
    )
    def test_general_and_disambiguated_course_lookup(
        self,
        course_query: str,
        expected_facts: list[str],
    ) -> None:
        out = answer(course_query, mode="chrono_rag")
        assert key_fact_score(out["predicted_answer"], expected_facts) == 1.0
        assert "Nhập môn công nghệ số" not in out["predicted_answer"]

    def test_unknown_course_abstains(self) -> None:
        out = answer("Môn Vũ trụ học lượng tử có bao nhiêu tín chỉ?", mode="chrono_rag")
        assert "không tìm thấy thông tin" in out["predicted_answer"].lower()
        assert out["cited_doc_ids"] == []

    def test_non_superseding_docs_have_accurate_temporal_prefix(self) -> None:
        out_pay = answer("Sinh viên không nộp học phí từ bao nhiêu học kỳ trở lên sẽ bị xem xét buộc thôi học?", mode="chrono_rag")
        assert "thay cho quy định cũ" not in out_pay["predicted_answer"].lower()
        assert "ban hành năm 2021" in out_pay["predicted_answer"].lower()

        out_tkb = answer("Tiết 13 buổi tối tại UET bắt đầu và kết thúc lúc mấy giờ?", mode="chrono_rag")
        assert "thay cho quy định cũ" not in out_tkb["predicted_answer"].lower()
        assert out_tkb["predicted_answer"].startswith("Theo thời khóa biểu năm học 2022-2023:")

        out_hist = answer("Học kỳ phụ năm học 2024-2025 diễn ra từ ngày nào đến ngày nào?", mode="chrono_rag")
        assert "thay cho quy định cũ" not in out_hist["predicted_answer"].lower()

    def test_section2_answer_quality_refinements(self, rag_adapter: RAGEvalAdapter) -> None:
        # 2.1: No trailing unrelated Điều 4 or older cohort lines
        q1 = "Các học phần học trong học kỳ hè được tính vào học kỳ nào để xét học bổng khuyến khích học tập năm 2026?"
        out1 = answer(q1, mode="chrono_rag")
        assert "học kỳ 2" in out1["predicted_answer"].lower()
        assert "[Điều 4]" not in out1["predicted_answer"]

        q8 = "Ngành Trí tuệ nhân tạo khóa QH-2025 trở đi có tổng cộng bao nhiêu tín chỉ?"
        out8 = answer(q8, mode="chrono_rag")
        assert "135 tín chỉ" in out8["predicted_answer"]
        assert "123 tín chỉ" not in out8["predicted_answer"]
        assert "124 tín chỉ" not in out8["predicted_answer"]

        # 2.2: Correct [Điều 5] label and merged Cách 3 (Phòng 101B-E3)
        q5 = "Nếu không chuyển khoản được học phí thì sinh viên nộp tiền mặt trực tiếp ở phòng nào?"
        out5 = answer(q5, mode="chrono_rag")
        assert "[Điều 5]" in out5["predicted_answer"]
        assert "101b-e3" in out5["predicted_answer"].lower()

        # 2.3: Clean boundary truncation (never ends mid-word like ', T')
        q_cntt = "Ngành Công nghệ thông tin có những môn học nào?"
        out_cntt = answer(q_cntt, mode="chrono_rag")
        assert not out_cntt["predicted_answer"].endswith(", T")
        assert out_cntt["predicted_answer"].endswith(".")

        # 2.4: TKB virtual curriculum doc_ids preserve 'd' for 'đ' and split sticky OCR words
        doc_ids = set(rag_adapter.retriever.doc_lines.keys())
        assert "uet-ctdt-cong-nghe-ky-thuat-dien-tu-vien-thong-tkb" in doc_ids
        assert "uet-ctdt-ky-thuat-may-tinh-tkb" in doc_ids
        assert "uet-ctdt-co-hoc-ky-thuat-tkb" in doc_ids
        assert "uet-ctdt-cong-nghe-thong-tin-dinh-huong-thi-truong-nhat-ban-tkb" in doc_ids
        assert "uet-ctdt-kythuat-ieu-khien-va-tu-ong-hoa-tkb" not in doc_ids

    def test_section3_governance_and_effective_dates(self, rag_adapter: RAGEvalAdapter) -> None:
        from src.rag.eval_adapter import InMemoryRetriever

        # 3.1a: Unreviewed curricula carry warning notice when warn_unreviewed=True
        out_ds = answer("Ngành Khoa học dữ liệu gồm bao nhiêu tín chỉ?", mode="chrono_rag")
        assert "chưa duyệt độc lập" in out_ds["predicted_answer"]

        # 3.1b: Strict mode (respect_retrieval_eligible=True) excludes all unreviewed manifest curricula
        strict_ret = InMemoryRetriever.from_corpus(respect_retrieval_eligible=True)
        assert not any(did.startswith(("uet-curriculum-", "uet-tuan-")) for did in strict_ret.doc_lines)
        assert "uet-ctdt-cong-nghe-thong-tin-tkb" in strict_ret.doc_lines
        # Strict mode must abstain on total-credit query for TKB-only majors instead of returning a 3 TC course
        strict_adapter = RAGEvalAdapter(strict_ret)
        strict_httt = strict_adapter.run_benchmark(
            [{"id": "strict_httt", "question": "Ngành Hệ thống thông tin khóa QH-2022 gồm bao nhiêu tín chỉ?"}],
            mode="chrono_rag",
        )[0]
        assert strict_httt["cited_doc_ids"] == []
        assert "không tìm thấy thông tin" in strict_httt["predicted_answer"].lower()

        # 3.2a: AI QH-2022–2024 surfaces both original (124 TC) and updated (123 TC) with unconfirmed date note
        out_ai22 = answer("Ngành Trí tuệ nhân tạo khóa QH-2022 gồm bao nhiêu tín chỉ?", mode="chrono_rag")
        assert "124 tín chỉ" in out_ai22["predicted_answer"]
        assert "123 tín chỉ" in out_ai22["predicted_answer"]
        assert "chưa được xác định" in out_ai22["predicted_answer"].lower()

        # 3.2b: Space Engineering QH-2022–2024 flags mismatched outcomes URL when asked about Chuẩn đầu ra / PLO
        out_space = answer("Chuẩn đầu ra ngành Công nghệ hàng không vũ trụ khóa QH-2022 như thế nào?", mode="chrono_rag")
        assert "vật lý kỹ thuật" in out_space["predicted_answer"].lower()

        # 3.3: Effective dates loaded from reviewed_documents.jsonl & date-aware filtering before 2026-08-07
        kkht26_meta = rag_adapter.retriever.doc_meta["uet-2026-quy-dinh-xet-hoc-bong-kkht-2026-17a091722e"]
        assert kkht26_meta["effective_from"] == "2026-08-07"
        out_before = answer(
            "Tính đến ngày 01/05/2026, quy định xét học bổng KKHT nào đang áp dụng?",
            mode="chrono_rag",
        )
        assert "uet-2026-quy-dinh-xet-hoc-bong-kkht-2026-17a091722e" not in out_before["cited_doc_ids"]

    @pytest.mark.parametrize(
        ("unseen_query", "expected_facts", "should_abstain"),
        [
            (
                "Các học phần học trong học kỳ hè được tính vào học kỳ nào để xét học bổng khuyến khích học tập năm 2026?",
                ["học kỳ 2"],
                False,
            ),
            (
                "Khi xét học bổng KKHT năm 2026, nếu hai sinh viên có cùng điểm học tập hệ 4 và cùng điểm rèn luyện mà kinh phí không đủ thì chọn ai?",
                ["nhiều tín chỉ hơn", "hệ 10"],
                False,
            ),
            (
                "Sinh viên đang hưởng trợ cấp xã hội hoặc học bổng chính sách có được xét học bổng khuyến khích học tập không?",
                ["vẫn được xét", "trợ cấp xã hội"],
                False,
            ),
            (
                "Sinh viên không nộp học phí từ bao nhiêu học kỳ trở lên sẽ bị xem xét buộc thôi học?",
                ["hai học kỳ", "buộc thôi học"],
                False,
            ),
            (
                "Nếu không chuyển khoản được học phí thì sinh viên nộp tiền mặt trực tiếp ở phòng nào?",
                ["101B-E3", "Phòng Kế hoạch - Tài chính"],
                False,
            ),
            (
                "Học kỳ phụ năm học 2026-2027 diễn ra từ ngày nào đến ngày nào?",
                ["05/07/2027", "29/08/2027"],
                False,
            ),
            (
                "Tiết 13 buổi tối tại UET bắt đầu và kết thúc lúc mấy giờ?",
                ["19h00", "19h50"],
                False,
            ),
            (
                "Ngành Trí tuệ nhân tạo khóa QH-2025 trở đi có tổng cộng bao nhiêu tín chỉ?",
                ["135 tín chỉ"],
                False,
            ),
            (
                "Học phần MAT1041 Giải tích 1 có mấy tín chỉ?",
                ["Giải tích 1", "MAT1041", "4"],
                False,
            ),
            (
                "Môn Trí tuệ nhân tạo có mấy tín chỉ?",
                ["Trí tuệ nhân tạo", "INT3401", "3"],
                False,
            ),
            (
                "Tiền thuê phòng ký túc xá Mỹ Đình của ĐHQGHN năm 2026 là bao nhiêu một tháng?",
                [],
                True,
            ),
            (
                "Ngành An toàn thông tin khóa QH-2025 tại UET cần tích lũy bao nhiêu tín chỉ?",
                [],
                True,
            ),
        ],
    )
    def test_twelve_unseen_student_queries_section5(
        self,
        unseen_query: str,
        expected_facts: list[str],
        should_abstain: bool,
    ) -> None:
        out = answer(unseen_query, mode="chrono_rag")
        if should_abstain:
            assert "không tìm thấy thông tin" in out["predicted_answer"].lower()
            assert out["cited_doc_ids"] == []
        else:
            assert key_fact_score(out["predicted_answer"], expected_facts) == 1.0

    def test_section4_modular_hybrid_llm_and_formatter(self) -> None:
        from src.rag.grounding import verify_llm_grounding
        from src.rag.hybrid import HybridDenseIndex, reciprocal_rank_fusion
        from src.rag.intent import detect_topic as intent_detect_topic, parse_temporal_intent as intent_parse_temporal
        from src.rag.lexicon import load_lexicon

        # 4.1: Externalized lexicon & modular intent imports
        lex = load_lexicon()
        assert "typo_map" in lex and "query_synonyms" in lex
        assert intent_detect_topic("Học kỳ phụ năm học 2026-2027 diễn ra từ ngày nào?") == "academic_calendar"
        assert intent_parse_temporal("Học phí năm học 2025-2026?") == ("temporal_specific", 2025)

        # 4.2: mode="chrono_rag_llm" grounded pass-through and hallucination fallback
        q_llm = "Mức học phí tín chỉ khóa QH-2023 hệ chuẩn năm học 2026-2027 là bao nhiêu?"
        out_ok = answer(
            q_llm,
            mode="chrono_rag_llm",
            llm_fn=lambda q, hits, plan, cfg: "Theo quy định năm học 2026-2027, khóa QH-2023 hệ chuẩn đóng 974.000 đồng/tín chỉ.",
        )
        assert out_ok["llm_used"] is True
        assert "974.000" in out_ok["predicted_answer"]

        # Hallucinated currency amount (9.999.000 not in context) must trigger fallback to extractive answer
        out_fb = answer(
            q_llm,
            mode="chrono_rag_llm",
            llm_fn=lambda q, hits, plan, cfg: "Theo quy định năm học 2026-2027, mức thu là 9.999.000 đồng/tín chỉ.",
        )
        assert out_fb["llm_used"] is False
        assert "9.999.000" not in out_fb["predicted_answer"]
        assert "974.000" in out_fb["predicted_answer"]
        assert verify_llm_grounding(q_llm, "9.999.000 đồng/tín chỉ", "974.000 đồng/tín chỉ", 30.0, {"học": 1.0}) is False

        # 4.3: Hybrid RRF merges BM25 + Dense hits cleanly with injected embed_fn
        mini_chunks = [
            {"chunk_id": "d1:0", "doc_id": "doc-tuition", "document": "Mức thu học phí đại học 974.000 đồng/tín chỉ", "metadata": {"doc_id": "doc-tuition"}},
            {"chunk_id": "d2:0", "doc_id": "doc-leave", "document": "Thủ tục bảo lưu kết quả học tập", "metadata": {"doc_id": "doc-leave"}},
        ]
        def _mock_embed(texts: list[str]) -> list[list[float]]:
            vecs = []
            for t in texts:
                tl = t.lower()
                vecs.append([1.0, 0.0] if ("học phí" in tl or "đóng tiền" in tl) else [0.0, 1.0])
            return vecs

        dense_idx = HybridDenseIndex(mini_chunks, embed_fn=_mock_embed)
        d_hits = dense_idx.query("sinh viên phải đóng tiền bao nhiêu?")
        assert d_hits and d_hits[0]["metadata"]["doc_id"] == "doc-tuition"
        fused = reciprocal_rank_fusion([], d_hits, top_k=2)
        assert fused and fused[0]["metadata"]["doc_id"] == "doc-tuition"

        out_hyb = answer("Học phí tín chỉ khóa QH-2023 năm 2026?", backend="hybrid", embed_fn=lambda ts: [[1.0] for _ in ts])
        assert out_hyb["debug"]["backend"] == "hybrid_v9"
        assert "974.000" in out_hyb["predicted_answer"]

        # 4.4: StudentHub _format_rag_answer keeps long legal clauses (>160 chars) intact
        import ast
        server_src = (REPO_ROOT / "src/api/studenthub_server.py").read_text(encoding="utf-8")
        tree = ast.parse(server_src)
        fmt_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_format_rag_answer")
        ns: dict[str, Any] = {"re": __import__("re")}
        exec(compile(ast.Module(body=[fmt_node], type_ignores=[]), "<fmt>", "exec"), ns)
        long_clause = (
            "Điểm trung bình chung học kỳ để xét học bổng khuyến khích học tập được tính từ điểm thi, "
            "kiểm tra hết môn học lần thứ nhất trong học kỳ của các học phần nằm trong khung chương trình "
            "đào tạo tính đến thời điểm xét học bổng (bao gồm cả các học phần học lại, học cải thiện)."
        )
        assert len(long_clause) > 160
        formatted = ns["_format_rag_answer"](f"Ngắn | {long_clause}")
        assert "điểm thi, kiểm tra hết môn học" in formatted.lower()

    @pytest.mark.parametrize(
        "ood_query",
        [
            "Ngành Y khoa có những môn học nào?",
            "Học phí ngành Y khoa là bao nhiêu?",
            "Điểm chuẩn ngành Y đa khoa Đại học Y Hà Nội năm 2024 là bao nhiêu?",
            "Ký túc xá Mễ Trì thu tiền điện nước bao nhiêu một số?",
            "Thời tiết Hà Nội hôm nay thế nào?",
            "Giá vàng SJC hôm nay bao nhiêu?",
        ],
    )
    def test_unsupported_and_ood_queries_abstain(self, ood_query: str) -> None:
        out = answer(ood_query, mode="chrono_rag")
        assert out["cited_doc_ids"] == []
        assert "Không tìm thấy thông tin phù hợp" in out["predicted_answer"]

    def test_restored_admissions_and_training_rules_markdown_queries(self) -> None:
        out_adm = answer("Điểm chuẩn UET năm 2024 là bao nhiêu?", mode="chrono_rag")
        assert out_adm["as_of_year"] == 2024
        assert "thong_bao_diem_trung_tuyen_2024" in out_adm["cited_doc_ids"]

        # General cutoff query without a specific major returns complete 20-major summary
        out_all_26 = answer("Điểm chuẩn đại học năm 2026?", mode="chrono_rag")
        assert out_all_26["as_of_year"] == 2026
        assert "thong_bao_diem_trung_tuyen_2026" in out_all_26["cited_doc_ids"]
        assert key_fact_score(out_all_26["predicted_answer"], ["20 ngành", "CN1", "CN12", "CN14", "CN20", "CN21"]) == 1.0

        for q_cut, exp_doc, exp_yr, exp_facts in [
            (
                "Điểm chuẩn thi ngành Hệ thống thông tin năm 2025?",
                "diem_trung_tuyen_2025",
                2025,
                ["Hệ thống thông tin", "CN14", "26.38"],
            ),
            (
                "Điểm chuẩn ngành Hệ thống thông tin năm 2026 là bao nhiêu?",
                "thong_bao_diem_trung_tuyen_2026",
                2026,
                ["Hệ thống thông tin", "CN14", "25,85"],
            ),
            (
                "Điểm chuẩn ngành Hệ thống thông tin năm 2024?",
                "thong_bao_diem_trung_tuyen_2024",
                2024,
                ["Hệ thống thông tin", "CN14", "26,87"],
            ),
            (
                "Điểm trúng tuyển ngành Hệ thống thông tin năm 2023?",
                "thong_bao_diem_trung_tuyen_theo_thpt_2023",
                2023,
                ["Hệ thống thông tin", "CN14", "26.95"],
            ),
            (
                "Điểm chuẩn ngành Hệ thống thông tin năm 2022 theo THPT là bao nhiêu?",
                "diem_trung_tuyen_2022",
                2022,
                ["Hệ thống thông tin", "CN14", "25"],
            ),
        ]:
            res_c = answer(q_cut, mode="chrono_rag")
            assert res_c["as_of_year"] == exp_yr
            assert exp_doc in res_c["cited_doc_ids"]
            assert key_fact_score(res_c["predicted_answer"], exp_facts) == 1.0

        out_rule = answer("Sinh viên bị cảnh báo học vụ khi nào?", mode="chrono_rag")
        assert any("quy_che_dao_tao" in d.lower() for d in out_rule["cited_doc_ids"])

    @pytest.mark.parametrize(
        ("cur_query", "expected_facts", "should_abstain"),
        [
            (
                "Ngành Hệ thống thông tin khóa QH-2022 gồm bao nhiêu tín chỉ?",
                ["Hệ thống thông tin", "136 tín chỉ", "chưa duyệt độc lập"],
                False,
            ),
            (
                "Ngành Hệ thống thông tin khóa QH-2025 gồm bao nhiêu tín chỉ?",
                [],
                True,
            ),
            (
                "Ngành Công nghệ thông tin khóa QH-2022 gồm bao nhiêu tín chỉ?",
                ["Công nghệ thông tin", "136 tín chỉ"],
                False,
            ),
            (
                "Ngành Công nghệ thông tin khóa QH-2025 gồm bao nhiêu tín chỉ?",
                ["Công nghệ thông tin", "135 tín chỉ"],
                False,
            ),
            (
                "Ngành Công nghệ thông tin gồm bao nhiêu tín chỉ?",
                ["Công nghệ thông tin", "135 tín chỉ"],
                False,
            ),
            (
                "Ngành Công nghệ thông tin chất lượng cao gồm bao nhiêu tín chỉ?",
                [],
                True,
            ),
            (
                "Ngành CNTT CLC gồm bao nhiêu tín chỉ?",
                [],
                True,
            ),
            (
                "Ngành CNTT Nhật Bản gồm bao nhiêu tín chỉ?",
                [],
                True,
            ),
            (
                "Ngành Khoa học máy tính khóa QH-2022 gồm bao nhiêu tín chỉ?",
                ["Khoa học máy tính", "136 tín chỉ"],
                False,
            ),
            (
                "Ngành Kỹ thuật máy tính khóa QH-2022 gồm bao nhiêu tín chỉ?",
                ["Kỹ thuật máy tính", "150 tín chỉ"],
                False,
            ),
            (
                "Ngành Kỹ thuật Robot khóa QH-2025 gồm bao nhiêu tín chỉ?",
                ["Kỹ thuật Robot", "150 tín chỉ"],
                False,
            ),
            (
                "Ngành Kỹ thuật điện tử viễn thông khóa QH-2025 gồm bao nhiêu tín chỉ?",
                ["135 tín chỉ"],
                False,
            ),
            (
                "Ngành Mạng máy tính và truyền thông dữ liệu khóa QH-2023 gồm bao nhiêu tín chỉ?",
                ["150 tín chỉ"],
                False,
            ),
        ],
    )
    def test_tuan_curricula_total_credits_and_grounding_guard(
        self,
        cur_query: str,
        expected_facts: list[str],
        should_abstain: bool,
    ) -> None:
        from src.rag.grounding import _verify_answer_grounding

        # Grounding guard must reject a single 3 TC elective line as an answer to a program total-credit query
        assert not _verify_answer_grounding(
            "Ngành Hệ thống thông tin khóa QH-2022 gồm bao nhiêu tín chỉ?",
            "Học phần Các hệ thống thương mại điện tử (môn tự chọn) (INT3506E, 3 TC)",
            35.0,
            {"hệ": 2.0, "thống": 2.0, "thông": 2.0, "tin": 2.0},
        )
        out = answer(cur_query, mode="chrono_rag")
        if should_abstain:
            assert out["cited_doc_ids"] == []
            assert "không tìm thấy thông tin" in out["predicted_answer"].lower()
        else:
            assert key_fact_score(out["predicted_answer"], expected_facts) == 1.0
            assert "3 TC" not in out["predicted_answer"]

    def test_retriever_loads_all_markdown_strictly_from_markdown_dir(
        self,
        rag_adapter: RAGEvalAdapter,
    ) -> None:
        meta_map = rag_adapter.retriever.doc_meta
        file_backed = [m for m in meta_map.values() if "source_path" in m]
        # 79 policy/calendar/research/admissions/training_rules docs + 31 official curricula + 48 non-excluded tuan wrappers = 158
        assert len(file_backed) == 158
        for m in file_backed:
            sp = m["source_path"]
            assert sp.startswith("data/raw/uet/markdown/"), f"Unexpected source_path outside markdown/: {sp}"
            assert "curricula/tuan_2022_2026/original/" not in sp
            assert (REPO_ROOT / sp).is_file()
        # None of the 5 owner-excluded wrappers may be loaded
        for excluded_id in (
            "uet-tuan-chuan-dau-ra-chuong-trinh-dao-tao-cntt-clc-2022-tro-di-338b06c6",
            "uet-tuan-chuan-dau-ra-chuong-trinh-dao-tao-cntt-nhat-ban-2022-tro-di-64d98214",
            "uet-tuan-gioi-thieu-chung-ve-chuong-trinh-dao-tao-cntt-clc-2022-tro-di-9bc2f86b",
            "uet-tuan-gioi-thieu-chung-ve-chuong-trinh-dao-tao-cntt-nhat-ban-2022-tro-di-297149ea",
            "uet-tuan-noi-dung-chuong-trinh-dao-tao-cntt-clc-2022-tro-di-60a2276b",
        ):
            assert excluded_id not in meta_map

    def test_audit_fixes_clean_clone_citations_rrf_and_curriculum_overview(
        self,
        tmp_path: Path,
    ) -> None:
        from src.rag.eval_adapter import InMemoryRetriever
        from src.rag.hybrid import reciprocal_rank_fusion

        # 1. Clean-clone test: works when gitignored documents.jsonl is absent
        (tmp_path / "data/raw/uet/markdown/2026").mkdir(parents=True)
        (tmp_path / "data/raw/uet/markdown/2026/Quy_dinh_muc_thu_hoc_phi_2026.md").write_text(
            "# Điều 1. Phạm vi\nHọc phí năm học 2026-2027 là 974.000 đồng/tín chỉ.",
            encoding="utf-8",
        )
        clean_ret = InMemoryRetriever.from_corpus(tmp_path)
        assert len(clean_ret.chunks) >= 1

        # 2. Hybrid RRF preserves multiple distinct chunks (articles) of the same doc_id
        bm25_multi = [
            {"chunk_id": "doc1:a1", "document": "Điều 1...", "score": 25.0, "metadata": {"doc_id": "doc1"}},
            {"chunk_id": "doc1:a5", "document": "Điều 5...", "score": 22.0, "metadata": {"doc_id": "doc1"}},
        ]
        fused_multi = reciprocal_rank_fusion(bm25_multi, [], top_k=4)
        assert len(fused_multi) == 2

        # 3. Article citation (dieu_so) is populated in pipeline output
        out_art = answer("Theo Điều 7 quy chế học bổng KKHT năm 2026, sinh viên cần tích lũy mấy tín chỉ?")
        assert out_art["sources"] and out_art["sources"][0]["dieu_so"] == "Điều 7"

        # 3b. Abolished-rule query with as_of_year=None resolves dynamically via supersession graph (no hardcoded year)
        out_abolished = answer(
            "Quy định phân chia sinh viên nước ngoài đóng 996.000 đ/tín chỉ (trừ Lào và Campuchia) đã bị bãi bỏ bằng nguyên tắc nào?"
        )
        assert out_abolished["as_of_year"] == 2025
        assert "QĐ 2080 và QĐ 2377" in out_abolished["predicted_answer"]

        # 4. General curriculum overview queries are consistent, include code + credits, and have no (CLC) leak
        for q_ov, exp_code, exp_tc in [
            ("Chương trình đào tạo ngành Hệ thống thông tin ?", "7480104", "136 tín chỉ"),
            ("Chương trình đào tạo ngành Công nghệ thông tin ?", "7480201", "135 tín chỉ"),
        ]:
            res_ov = answer(q_ov, mode="chrono_rag")
            assert res_ov["as_of_year"] == 2025
            assert exp_code in res_ov["predicted_answer"]
            assert exp_tc in res_ov["predicted_answer"]
            assert "(CLC)" not in res_ov["predicted_answer"]
            assert "(CNTT, AI)" not in res_ov["predicted_answer"]
            assert "đạt được các năng lực sau:" not in res_ov["predicted_answer"]

        # 5. Major-specific tuition queries resolve exact ĐMKTKT / CTĐT chuẩn tier without leaking HKVT/XDGT
        res_httt = answer("Học phí ngành Hệ thống thông tin?", mode="chrono_rag")
        assert res_httt["as_of_year"] == 2026
        assert key_fact_score(res_httt["predicted_answer"], ["Hệ thống thông tin", "CN14", "44.000.000", "4.400.000", "1.188.000"]) == 1.0
        assert "Hàng không vũ trụ" not in res_httt["predicted_answer"]
        assert "Xây dựng Giao thông" not in res_httt["predicted_answer"]
        assert "thong_tin_tuyen_sinh_2026" in res_httt["cited_doc_ids"]

        res_ai_fee = answer("Học phí ngành Trí tuệ nhân tạo?", mode="chrono_rag")
        assert res_ai_fee["as_of_year"] == 2026
        assert key_fact_score(res_ai_fee["predicted_answer"], ["Trí tuệ nhân tạo", "CN12", "38.000.000", "3.600.000", "974.000"]) == 1.0

        res_httt_25 = answer("Học phí ngành Hệ thống thông tin năm 2025?", mode="chrono_rag")
        assert res_httt_25["as_of_year"] == 2025
        assert key_fact_score(res_httt_25["predicted_answer"], ["Hệ thống thông tin", "40.000.000", "4.000.000", "1.079.000"]) == 1.0

        res_httt_qh22 = answer("Học phí ngành Hệ thống thông tin khóa QH-2022?", mode="chrono_rag")
        assert res_httt_qh22["as_of_year"] == 2026
        assert key_fact_score(res_httt_qh22["predicted_answer"], ["3.200.000", "860.000"]) == 1.0
        assert "Hàng không vũ trụ" not in res_httt_qh22["predicted_answer"]

        # 6. End-to-end Gemini API integration in chrono_rag_llm (grounded prose accepted, hallucinated figure rejected)
        import io
        import urllib.request

        class _MockGeminiHTTP:
            def __init__(self, reply_text: str) -> None:
                self._payload = json.dumps({
                    "candidates": [{"content": {"parts": [{"text": reply_text}]}}]
                }).encode("utf-8")

            def __enter__(self) -> "_MockGeminiHTTP":
                return self

            def __exit__(self, *args: Any) -> bool:
                return False

            def read(self) -> bytes:
                return self._payload

        orig_urlopen = urllib.request.urlopen
        try:
            urllib.request.urlopen = lambda req, timeout=30.0: _MockGeminiHTTP(  # type: ignore[assignment]
                "Theo Quyết định 2377/QĐ-ĐHCN và Thông tin tuyển sinh 2026, ngành Hệ thống thông tin (mã CN14) "
                "thuộc nhóm ĐMKTKT với mức học phí năm học 2026-2027 là 44.000.000 đồng/năm học "
                "(tương đương 4.400.000 đồng/tháng hoặc 1.188.000 đồng/tín chỉ)."
            )
            res_gem_ok = answer(
                "Học phí ngành Hệ thống thông tin?",
                mode="chrono_rag_llm",
                cfg={"top_k": 4, "llm": {"provider": "gemini", "model": "gemini-2.5-flash", "api_key": "fake-key"}},
            )
            assert res_gem_ok["llm_used"] is True
            assert "44.000.000 đồng/năm học" in res_gem_ok["answer"]

            # Hallucinated currency figure (99.000.000) is rejected by verify_llm_grounding -> safe extractive fallback
            urllib.request.urlopen = lambda req, timeout=30.0: _MockGeminiHTTP(  # type: ignore[assignment]
                "Ngành Hệ thống thông tin có mức học phí là 99.000.000 đồng/năm học."
            )
            res_gem_bad = answer(
                "Học phí ngành Hệ thống thông tin?",
                mode="chrono_rag_llm",
                cfg={"top_k": 4, "llm": {"provider": "gemini", "model": "gemini-2.5-flash", "api_key": "fake-key"}},
            )
            assert res_gem_bad["llm_used"] is False
            assert "44.000.000" in res_gem_bad["answer"]
            assert "99.000.000" not in res_gem_bad["answer"]
        finally:
            urllib.request.urlopen = orig_urlopen


# ==============================================================================
# 5. OUTDATED HALLUCINATION RATE (OHR) DEFENSE TESTS
# ==============================================================================
class TestOutdatedHallucinationDefense:
    """Verify OHR detection logic and ensure ChronoRAG never emits unflagged outdated traps."""

    def test_ohr_metric_flags_unwarned_outdated_numbers_and_years(self) -> None:
        # Unwarned trap number -> OHR = 1.0
        assert ohr_score(
            predicted="Mức học phí hiện hành là 1.850.000 đồng/tháng.",
            outdated_trap_answer="1.850.000 đồng/tháng (mức năm 2025-2026)",
            category="active_rule",
            target_year=2026,
            predicted_year=2026,
        ) == 1.0

        # Outdated year without disclaimer on active_rule -> OHR = 1.0
        assert ohr_score(
            predicted="Mức học phí áp dụng là 3.000.000 đồng/tháng.",
            outdated_trap_answer=None,
            category="active_rule",
            target_year=2026,
            predicted_year=2025,
        ) == 1.0

        # Properly disclaimed historical comparison -> OHR = 0.0
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
        violating = [
            d["id"] for d in chrono_eval_results["details"] if d["ohr_score"] > 0.0
        ]
        assert violating == [], f"Questions triggering OHR violation: {violating}"


# ==============================================================================
# 6. FULL BENCHMARK REGRESSION GATE (BY CATEGORY, TOPIC, AND YEAR)
# ==============================================================================
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
        assert cat_metrics["key_fact_score"] == 1.0, f"{category} Key-Fact < 1.0: {cat_metrics}"
        assert cat_metrics["temporal_score"] == 1.0, f"{category} Temporal < 1.0: {cat_metrics}"
        assert cat_metrics["ohr_rate"] == 0.0, f"{category} OHR > 0.0: {cat_metrics}"

    @pytest.mark.parametrize("topic", ["hoc_phi", "hoc_bong", "nckh", "dao_tao"])
    def test_100_percent_accuracy_per_topic(
        self,
        topic: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        topic_metrics = chrono_eval_results["by_topic"][topic]
        assert topic_metrics["key_fact_score"] == 1.0, f"Topic {topic} Key-Fact < 1.0: {topic_metrics}"
        assert topic_metrics["temporal_score"] == 1.0, f"Topic {topic} Temporal < 1.0: {topic_metrics}"
        assert topic_metrics["ohr_rate"] == 0.0, f"Topic {topic} OHR > 0.0: {topic_metrics}"

    @pytest.mark.parametrize("year", ["2022", "2023", "2024", "2025", "2026"])
    def test_100_percent_accuracy_per_target_year(
        self,
        year: str,
        chrono_eval_results: dict[str, Any],
    ) -> None:
        year_metrics = chrono_eval_results["by_year"][year]
        assert year_metrics["key_fact_score"] == 1.0, f"Year {year} Key-Fact < 1.0: {year_metrics}"
        assert year_metrics["temporal_score"] == 1.0, f"Year {year} Temporal < 1.0: {year_metrics}"
        assert year_metrics["ohr_rate"] == 0.0, f"Year {year} OHR > 0.0: {year_metrics}"