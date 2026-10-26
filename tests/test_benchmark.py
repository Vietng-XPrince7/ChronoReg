"""
Test suite cho bộ dữ liệu Benchmark của ChronoReg.
Kiểm tra tính toàn vẹn schema, số lượng câu hỏi (>= 85 câu), tính chính xác của doc_id và SHA256,
và sự phân bổ cân đối giữa 3 categories: active_rule, superseded_rule, temporal_specific.
"""

import json
from pathlib import Path
import pytest

BENCHMARK_JSON = Path("data/benchmark/uet_regulation_benchmark.json")
BENCHMARK_JSONL = Path("data/qa_benchmark/benchmark.jsonl")
VALID_JSONL = Path("data/qa_benchmark/valid.jsonl")
SUPERSEDED_JSONL = Path("data/qa_benchmark/superseded.jsonl")
YEAR_SPECIFIC_JSONL = Path("data/qa_benchmark/year_specific.jsonl")
REVIEWED_DOCS = Path("data/versioning/reviewed_documents.jsonl")

REQUIRED_KEYS = [
    "id", "question", "category", "topic", "target_year",
    "ground_truth_answer", "key_facts", "outdated_trap_answer",
    "source_doc_id", "source_clause", "source_sha256"
]

REQUIRED_LORA_KEYS = [
    "id", "question", "type", "as_of_year", "gold_answer", "gold_doc_id", "outdated_answer"
]


@pytest.fixture(scope="module")
def registry():
    with open(REVIEWED_DOCS, encoding="utf-8") as f:
        return {item["doc_id"]: item["content_sha256"] for item in [json.loads(line) for line in f]}


@pytest.fixture(scope="module")
def benchmark_data():
    assert BENCHMARK_JSON.exists(), f"Không tìm thấy {BENCHMARK_JSON}"
    with open(BENCHMARK_JSON, encoding="utf-8") as f:
        return json.load(f)


def test_benchmark_quantity(benchmark_data):
    """Đảm bảo số lượng câu hỏi >= 85 câu theo yêu cầu."""
    assert len(benchmark_data) >= 85, f"Số câu hỏi {len(benchmark_data)} < 85"


def test_benchmark_schema(benchmark_data):
    """Kiểm tra schema bắt buộc của từng câu hỏi trong benchmark."""
    seen_ids = set()
    for item in benchmark_data:
        # 1. Các trường bắt buộc
        for k in REQUIRED_KEYS:
            assert k in item, f"Câu hỏi {item.get('id')} thiếu trường '{k}'"
            if k != "outdated_trap_answer":
                assert item[k] is not None and str(item[k]).strip() != "", f"Trường '{k}' rỗng ở câu {item.get('id')}"

        # 2. ID không được trùng lặp
        assert item["id"] not in seen_ids, f"ID trùng lặp: {item['id']}"
        seen_ids.add(item["id"])

        # 3. Category hợp lệ
        assert item["category"] in ["active_rule", "superseded_rule", "temporal_specific"]

        # 4. Key facts phải là list không rỗng
        assert isinstance(item["key_facts"], list) and len(item["key_facts"]) > 0

        # 5. Target year là số nguyên hợp lệ
        assert isinstance(item["target_year"], int) and 2021 <= item["target_year"] <= 2027


def test_benchmark_source_provenance_and_sha(benchmark_data, registry):
    """Đảm bảo mọi source_doc_id tồn tại trong versioning registry và source_sha256 khớp 100%."""
    for item in benchmark_data:
        doc_id = item["source_doc_id"]
        sha = item["source_sha256"]
        assert doc_id in registry, f"doc_id '{doc_id}' không có trong reviewed_documents.jsonl"
        assert sha == registry[doc_id], f"SHA không khớp cho {doc_id}: benchmark={sha[:10]}, registry={registry[doc_id][:10]}"


def test_benchmark_category_distribution(benchmark_data):
    """Kiểm tra phân bổ đủ 3 nhóm: active_rule, superseded_rule, temporal_specific."""
    counts = {}
    for item in benchmark_data:
        c = item["category"]
        counts[c] = counts.get(c, 0) + 1

    assert counts.get("active_rule", 0) >= 30, f"active_rule quá ít: {counts.get('active_rule')}"
    assert counts.get("superseded_rule", 0) >= 20, f"superseded_rule quá ít: {counts.get('superseded_rule')}"
    assert counts.get("temporal_specific", 0) >= 20, f"temporal_specific quá ít: {counts.get('temporal_specific')}"


def test_lora_compatible_benchmark_file():
    """Kiểm tra file benchmark.jsonl tương thích chuẩn LoRA pipeline."""
    assert BENCHMARK_JSONL.exists()
    lines = [json.loads(l) for l in BENCHMARK_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 85
    for row in lines:
        for k in REQUIRED_LORA_KEYS:
            assert k in row, f"Thiếu key '{k}' cho LoRA contract ở ID {row.get('id')}"


def test_split_files_exist_and_consistent():
    """Kiểm tra các file split valid.jsonl, superseded.jsonl, year_specific.jsonl."""
    assert VALID_JSONL.exists()
    assert SUPERSEDED_JSONL.exists()
    assert YEAR_SPECIFIC_JSONL.exists()

    v_lines = [json.loads(l) for l in VALID_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    s_lines = [json.loads(l) for l in SUPERSEDED_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    y_lines = [json.loads(l) for l in YEAR_SPECIFIC_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]

    assert all(r["category"] == "active_rule" for r in v_lines)
    assert all(r["category"] == "superseded_rule" for r in s_lines)
    assert all(r["category"] == "temporal_specific" for r in y_lines)
    assert len(v_lines) + len(s_lines) + len(y_lines) >= 85


def test_anti_data_leakage_between_train_and_benchmark():
    """Đảm bảo KHÔNG có câu hỏi nào trong tập Training QA của LoRA trùng lặp quá 75% với 90 câu Benchmark."""
    import re
    train_qa_path = Path("src/lora/runs/approved_qa.jsonl")
    assert train_qa_path.exists(), "Chưa tìm thấy src/lora/runs/approved_qa.jsonl"
    
    train_rows = [json.loads(l) for l in train_qa_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    bench_rows = [json.loads(l) for l in BENCHMARK_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    
    assert len(train_rows) >= 150, f"Số câu train QA {len(train_rows)} < 150"
    assert len(bench_rows) >= 85
    
    def word_set(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))
    
    bench_word_sets = [(b["id"], b["question"], word_set(b["question"])) for b in bench_rows]
    
    for train_item in train_rows:
        t_id = train_item["id"]
        t_q = train_item["question"]
        t_words = word_set(t_q)
        
        for b_id, b_q, b_words in bench_word_sets:
            if not t_words or not b_words:
                continue
            jaccard_sim = len(t_words & b_words) / len(t_words | b_words)
            assert jaccard_sim < 0.75, (
                f"Phát hiện Data Leakage giữa Train '{t_id}' và Benchmark '{b_id}'!\n"
                f"Similarity: {jaccard_sim:.2f} >= 0.75\n"
                f"Train Question: {t_q}\n"
                f"Benchmark Question: {b_q}"
            )


