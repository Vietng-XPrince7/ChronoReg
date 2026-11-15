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
    """Check the genuinely released QLoRA 3B QA; never restore old fake rows.

    Without a released dataset, this data-dependent check cannot run.
    The training release gate remains closed; no unreviewed QA is accepted.
    """
    import hashlib
    import re
    from src.lora.contracts import read_jsonl, validate_benchmark, validate_training

    repo = Path.cwd()
    old_demo = repo / "src/lora/runs/approved_qa.jsonl"
    assert not old_demo.exists(), (
        "Retired 0.5B pseudo-approved QA reappeared; do not use for 3B training"
    )
    config = (repo / "configs/lora.yaml").read_text(encoding="utf-8")
    assert "Qwen/Qwen2.5-3B-Instruct" in config, "Canonical model must be 3B"

    release_path = repo / "docs/lora_releases/qlora3b_release.json"
    if not release_path.is_file():
        pytest.skip(
            "3B training dataset not owner-released yet; "
            "leakage comparison needs a genuine approved dataset"
        )

    release = json.loads(release_path.read_text(encoding="utf-8-sig"))
    assert release.get("schema") == "chronoreg-qlora3b-release/v1"
    assert release.get("status") == "owner_released"
    assert release.get("independent_training_review") is True
    assert release.get("independent_benchmark_review") is True
    assert release.get("semantic_leakage_reviewed") is True

    relative = Path(release.get("curated_train_file", ""))
    assert not relative.is_absolute() and str(relative).strip()
    train_path = (repo / relative).resolve()
    assert train_path.is_relative_to(repo.resolve()), "Training path escapes repo"
    assert train_path.is_file(), "Released curated 3B QA file missing"
    assert hashlib.sha256(train_path.read_bytes()).hexdigest() == release.get(
        "curated_train_sha256"
    ), "Released 3B QA SHA256 mismatch"

    benchmark_rows = validate_benchmark(read_jsonl(BENCHMARK_JSONL))
    assert len(benchmark_rows) == 90
    approved = validate_training(read_jsonl(train_path), repo, benchmark_rows)
    assert len(approved) >= 200, "QLoRA 3B requires >= 200 approved QA"
    for year in (2022, 2023, 2024, 2025, 2026):
        assert sum(row["as_of_year"] == year for row in approved) >= 30, (
            f"Insufficient approved QA for {year}"
        )

    def word_set(value: str) -> set[str]:
        return set(re.findall(r"\w+", value.lower()))

    bench_words = [(r["id"], word_set(r["question"])) for r in benchmark_rows]
    for item in approved:
        words = word_set(item["question"])
        for bid, gold in bench_words:
            if not words or not gold:
                continue
            similarity = len(words & gold) / len(words | gold)
            assert similarity < 0.75, (
                f"Potential train/benchmark question leakage "
                f"{item['id']} vs {bid} (Jaccard={similarity:.3f})"
            )
