"""Unit tests cho các chỉ số định lượng trong src/eval/metrics.py."""
import pytest
from src.eval.metrics import (
    compute_forgetting_matrix,
    exact_match,
    key_fact_score,
    latency_stats,
    normalize_vietnamese,
    ohr_score,
    temporal_accuracy,
    token_f1,
)


def test_normalize_vietnamese_currency_and_years():
    # Chuẩn hóa tiền tệ
    assert "1850000" in normalize_vietnamese("Mức học phí là 1.850.000đ mỗi tháng.")
    assert "1850000" in normalize_vietnamese("Mức học phí là 1,850,000 đồng / tháng.")
    assert "2200000" in normalize_vietnamese("2.200.000 VNĐ")

    # Chuẩn hóa năm học
    assert "2023-2024" in normalize_vietnamese("Áp dụng cho năm học 2023 - 2024.")
    assert "2024-2025" in normalize_vietnamese("Năm học 2024/2025")

    # Xử lý chuỗi rỗng
    assert normalize_vietnamese("") == ""
    assert normalize_vietnamese(None) == ""


def test_key_fact_score_full_and_partial():
    key_facts = ["1.850.000 đồng", "ngành CNTT", "Quyết định 4618/QĐ-ĐHQGHN"]

    # Đầy đủ facts (3 / 3)
    ans_perfect = "Theo Quyết định 4618/QĐ-ĐHQGHN, học phí ngành CNTT là 1.850.000đ/tháng."
    assert key_fact_score(ans_perfect, key_facts) == 1.0

    # Một phần facts (2 / 3: khớp '1.850.000 đồng' và 'ngành CNTT')
    ans_partial = "Mức học phí ngành CNTT là 1.850.000 đồng theo quy định hiện hành."
    score = key_fact_score(ans_partial, key_facts)
    assert 0.6 <= score <= 0.7  # 2/3 ~ 0.6667

    # Không chứa fact nào (0 / 3)
    ans_none = "Nhà trường chưa có thông báo cụ thể về vấn đề này."
    assert key_fact_score(ans_none, key_facts) == 0.0

    # Edge cases
    assert key_fact_score("Bất kỳ câu nào", []) == 1.0
    assert key_fact_score("", key_facts) == 0.0


def test_token_f1():
    # Trùng khớp hoàn toàn
    assert token_f1("Học phí là 1.850.000đ", "Học phí là 1.850.000 đồng") == 1.0

    # Trùng khớp một phần
    f1 = token_f1("Sinh viên ngành Công nghệ thông tin", "Sinh viên Công nghệ thông tin định hướng Nhật Bản")
    assert 0.0 < f1 < 1.0

    # Không có từ nào trùng (hoàn toàn phân biệt)
    assert token_f1("Học phí sinh viên", "Đề tài nghiên cứu") == 0.0

    # Edge cases chuỗi rỗng
    assert token_f1("", "") == 1.0
    assert token_f1("Có nội dung", "") == 0.0
    assert token_f1("", "Có nội dung") == 0.0


def test_exact_match():
    assert exact_match("Học phí: 1.850.000đ", "Học phí 1.850.000 đồng") == 1.0
    assert exact_match("Đạt chuẩn C1", "Đạt chuẩn B2") == 0.0


def test_temporal_accuracy():
    gold_doc = "QD-4618-DHQGHN"
    gold_year = 2024

    # Đúng cả doc_id và năm học
    res_both = temporal_accuracy(
        predicted_answer="Theo quy định năm học 2024-2025 trong văn bản QD-4618-DHQGHN...",
        gold_doc_id=gold_doc,
        gold_year=gold_year,
        cited_doc_ids=["QD-4618-DHQGHN"],
        predicted_year=2024,
    )
    assert res_both["doc_correct"] is True
    assert res_both["year_correct"] is True
    assert res_both["score"] == 1.0

    # Chỉ đúng doc_id qua cited_doc_ids, sai năm
    res_doc_only = temporal_accuracy(
        predicted_answer="Áp dụng cho sinh viên năm 2022.",
        gold_doc_id=gold_doc,
        gold_year=gold_year,
        cited_doc_ids=["QD-4618-DHQGHN"],
        predicted_year=2022,
    )
    assert res_doc_only["doc_correct"] is True
    assert res_doc_only["year_correct"] is False
    assert res_doc_only["score"] == 0.5

    # Sai cả hai
    res_neither = temporal_accuracy(
        predicted_answer="Theo quy định năm 2021 trong QD-1234...",
        gold_doc_id=gold_doc,
        gold_year=gold_year,
        cited_doc_ids=["QD-9999"],
        predicted_year=2021,
    )
    assert res_neither["doc_correct"] is False
    assert res_neither["year_correct"] is False
    assert res_neither["score"] == 0.0


def test_ohr_score_detects_outdated_hallucination():
    trap = "Mức học phí cũ là 980.000 đồng/tháng theo quy định năm 2021."

    # Trả lời bẫy số tiền lỗi thời
    ans_hallucinated = "Học phí áp dụng hiện tại là 980.000đ một tháng."
    assert ohr_score(ans_hallucinated, trap) == 1.0

    # Trả lời sạch với quy định mới
    ans_clean = "Học phí hiện nay là 1.850.000đ/tháng theo quyết định mới nhất."
    assert ohr_score(ans_clean, trap) == 0.0

    # Không có bẫy
    assert ohr_score("Bất kỳ câu trả lời nào", None) == 0.0
    assert ohr_score("", trap) == 0.0

    # Có disclaimer tuyên bố quy định cũ -> Miễn trừ OHR
    ans_disclaimed = "Theo quy định cũ trước đây mức học phí là 980.000đ/tháng, nay đã bị thay thế."
    assert ohr_score(ans_disclaimed, trap) == 0.0

    # Quy tắc (b): active_rule nhưng trích xuất văn bản năm cũ không có cảnh báo
    ans_old_doc = "Mức thu học phí là 1.200.000 đồng/tháng."
    assert ohr_score(ans_old_doc, outdated_trap_answer=None, category="active_rule", target_year=2026, predicted_year=2022) == 1.0
    # Nếu có cảnh báo quy định cũ -> Miễn trừ
    ans_old_with_warning = "Theo quy định cũ trước đây, mức thu là 1.200.000 đồng/tháng."
    assert ohr_score(ans_old_with_warning, outdated_trap_answer=None, category="active_rule", target_year=2026, predicted_year=2022) == 0.0


def test_compute_forgetting_matrix():
    # Kịch bản học tuần tự qua 3 năm: 2022 -> 2023 -> 2024
    stage_results = {
        2022: {2022: 0.90},
        2023: {2022: 0.80, 2023: 0.92},  # Quên 0.10 ở năm 2022
        2024: {2022: 0.70, 2023: 0.85, 2024: 0.95},  # Quên 0.20 ở năm 2022, 0.07 ở 2023
    }
    matrix = compute_forgetting_matrix(stage_results)
    assert "2023" in matrix["forgetting_drops"]
    assert matrix["forgetting_drops"]["2023"]["2022"] == 0.10
    assert matrix["forgetting_drops"]["2024"]["2022"] == 0.20
    assert matrix["forgetting_drops"]["2024"]["2023"] == 0.07
    assert matrix["mean_forgetting"] > 0.0
    assert matrix["backward_transfer"] < 0.0


def test_latency_stats():
    timings = [10.0, 20.0, 30.0, 40.0, 100.0]
    stats = latency_stats(timings)
    assert stats["count"] == 5
    assert stats["mean_ms"] == 40.0
    assert stats["median_ms"] == 30.0
    assert stats["min_ms"] == 10.0
    assert stats["max_ms"] == 100.0
    assert stats["p95_ms"] == 100.0

    # Empty
    empty_stats = latency_stats([])
    assert empty_stats["count"] == 0
    assert empty_stats["mean_ms"] == 0.0
