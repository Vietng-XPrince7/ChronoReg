"""Kiểm thử các hàm đo của src/rag/evaluate.py (không cần ChromaDB/model thật)."""
from src.rag import evaluate as ev
from tests.test_rag_retriever import CFG, fake_index


def test_numeric_facts_ignore_years_and_short_numbers():
    facts = ["1.350.000 đồng/tháng", "13.500.000 đồng/năm học", "367.000 đồng/tín chỉ",
             "năm học 2022-2023", "giảm 10%"]
    assert ev.numeric_facts(facts) == {"1350000", "13500000", "367000"}
    assert ev.fact_recall(facts, "mức 1.350.000 đ và 367.000 đ") == 2 / 3
    assert ev.fact_recall(["năm học 2022-2023"], "bất kỳ") is None


def test_expected_years_and_top1_status():
    sup = {"category": "superseded_rule", "target_year": 2025}
    assert ev.expected_years(sup) == {2025, 2026}
    assert ev.expected_years({"category": "temporal_specific", "target_year": 2022}) == {2022}
    hit = lambda y: [{"metadata": {"start_year": y}}]
    assert ev.top1_status(hit(2025), {2025}) == "correct"
    assert ev.top1_status(hit(2022), {2025}) == "outdated"
    assert ev.top1_status(hit(2026), {2025}) == "too_new"
    assert ev.top1_status(hit(0), {2025}) == "unknown_year"
    assert ev.top1_status([], {2025}) == "no_result"


def test_evaluate_end_to_end_with_fake_index():
    items = [
        {"id": "T1", "category": "temporal_specific", "target_year": 2022, "source_doc_id": "hp-2022",
         "question": "Năm học 2022-2023, định mức học phí đào tạo đại học là bao nhiêu?", "key_facts": []},
        {"id": "S1", "category": "superseded_rule", "target_year": 2022, "source_doc_id": "hp-2022",
         "question": "Trước năm học 2023-2024, định mức học phí năm học 2022-2023 là bao nhiêu?", "key_facts": []},
        {"id": "X1", "category": "temporal_specific", "target_year": 2023, "source_doc_id": "khong-co",
         "question": "Năm học 2023-2024, định mức học phí là bao nhiêu?", "key_facts": []},
    ]
    with fake_index():
        rows = ev.evaluate(items, CFG, "none")
    by = {r["id"]: r for r in rows}
    assert by["T1"]["hit_any"] and by["T1"]["top1"] == "correct" and by["T1"]["gold_indexed"]
    assert by["S1"]["hit_any"]                                   # nêu 2 năm học -> lấy cả hai
    assert not by["X1"]["gold_indexed"] and not by["X1"]["hit_any"]
    summ = ev.summarize(rows)
    assert summ["TỔNG"]["n"] == 3 and summ["TỔNG"]["gold_not_indexed"] == 1
