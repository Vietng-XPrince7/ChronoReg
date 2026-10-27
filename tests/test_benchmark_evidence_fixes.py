"""Evidence checks for the benchmark repair, pinned to the 2026-10-27 corpus.

Do not interpret a matching source string as independent human approval.
"""
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
CORRECTED = ["BENCH_ACT_017", "BENCH_ACT_018", "BENCH_ACT_020", "BENCH_ACT_022", "BENCH_ACT_024", "BENCH_ACT_025", "BENCH_ACT_026", "BENCH_ACT_027", "BENCH_ACT_030", "BENCH_ACT_031", "BENCH_ACT_032", "BENCH_ACT_033", "BENCH_ACT_034", "BENCH_ACT_036", "BENCH_ACT_037", "BENCH_SUP_006", "BENCH_SUP_007", "BENCH_SUP_009", "BENCH_SUP_010", "BENCH_SUP_013", "BENCH_SUP_014", "BENCH_SUP_015", "BENCH_SUP_016", "BENCH_SUP_017", "BENCH_SUP_018", "BENCH_SUP_026", "BENCH_SUP_027", "BENCH_TEM_005", "BENCH_TEM_006", "BENCH_TEM_007", "BENCH_TEM_008", "BENCH_TEM_009", "BENCH_TEM_010", "BENCH_TEM_011", "BENCH_TEM_012", "BENCH_TEM_016", "BENCH_TEM_017", "BENCH_TEM_018", "BENCH_TEM_019", "BENCH_TEM_020", "BENCH_TEM_021", "BENCH_TEM_022"]
SOURCE_ANCHORS = {'BENCH_ACT_017': ['ít nhất 15 tín chỉ'], 'BENCH_ACT_018': ['kết quả học tập, rèn luyện từ loại khá'], 'BENCH_ACT_020': ['4618/QĐ-ĐHQGHN'], 'BENCH_ACT_022': ['không thực hiện tốt trách nhiệm', 'thu hồi học bổng'], 'BENCH_ACT_024': ['447/QĐ-ĐHCN'], 'BENCH_ACT_025': ['22/04/2026'], 'BENCH_ACT_026': ['03/09/2026', '14/02/2027'], 'BENCH_ACT_027': ['07/09/2026', '13/09/2026'], 'BENCH_ACT_030': ['3.200.000', 'QH-2022'], 'BENCH_ACT_031': ['3.100.000', 'QH-2022'], 'BENCH_ACT_032': ['2.150.000', '3.200.000'], 'BENCH_ACT_033': ['21/09/2026', '27/09/2026'], 'BENCH_ACT_034': ['01/02/2027', '14/02/2027'], 'BENCH_ACT_036': ['18/20 ngành'], 'BENCH_ACT_037': ['23–27/03/2026'], 'BENCH_SUP_006': ['28.100.000', '765.000'], 'BENCH_SUP_007': ['32.000.000', '869.000'], 'BENCH_SUP_009': ['24.600.000', '767.000'], 'BENCH_SUP_010': ['36.000.000', '1.091.000'], 'BENCH_SUP_013': ['1388', '2.750.000'], 'BENCH_SUP_014': ['1.810.000', '1.880.000'], 'BENCH_SUP_015': ['thay thế cho các văn bản được ban hành trước đó'], 'BENCH_SUP_016': ['5249/QĐĐHQGHN', '27 tháng 12 năm 2014'], 'BENCH_SUP_017': ['22/02/2024', '12/03/2024'], 'BENCH_SUP_018': ['27/02/2025', '06–15/03/2025'], 'BENCH_SUP_026': ['3.580.000'], 'BENCH_SUP_027': ['2.680.000'], 'BENCH_TEM_005': ['20.250.000', '30.000.000'], 'BENCH_TEM_006': ['33.750.000', '36.000.000'], 'BENCH_TEM_007': ['18.700.000', '510.000'], 'BENCH_TEM_008': ['23.400.000', '634.000'], 'BENCH_TEM_009': ['33.000.000', '1.076.000'], 'BENCH_TEM_010': ['40.000.000', '1.218.000'], 'BENCH_TEM_011': ['2.610.000'], 'BENCH_TEM_012': ['2.315.000'], 'BENCH_TEM_016': ['2.200.000'], 'BENCH_TEM_017': ['2.600.000'], 'BENCH_TEM_018': ['24/04–04/05/2026'], 'BENCH_TEM_019': ['05/03/2026', '23–27/03/2026', '15/02/2026', '25/02/2026'], 'BENCH_TEM_020': ['Tháng 5/2023'], 'BENCH_TEM_021': ['07h00', '07h50'], 'BENCH_TEM_022': ['07/09/2026', '13/09/2026']}
UNCHANGED_48_DIGEST = "4321b8d07be1204e2029f798fa6aaf23cc59c0d76c7b78647ed4400409a3a421"


def _load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _jsonl(rel):
    return [json.loads(l) for l in (ROOT / rel).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_generator_matches_canonical_benchmark(monkeypatch):
    monkeypatch.chdir(ROOT)
    items = runpy.run_path(str(ROOT / "scripts/generate_benchmark_dataset.py"))["BENCHMARK_ITEMS"]
    assert items == _load("data/benchmark/uet_regulation_benchmark.json")


def test_all_benchmark_copies_match_and_keep_original_id_counts():
    rows = _load("data/benchmark/uet_regulation_benchmark.json")
    assert len(rows) == 90
    assert len({q["id"] for q in rows}) == 90
    assert len({q["question"] for q in rows}) == 90
    assert {k: sum(r["category"] == k for r in rows) for k in (
        "active_rule", "superseded_rule", "temporal_specific"
    )} == {"active_rule": 37, "superseded_rule": 27, "temporal_specific": 26}
    by_id = {x["id"]: x for x in rows}
    all_jsonl = _jsonl("data/qa_benchmark/benchmark.jsonl")
    assert [x["id"] for x in all_jsonl] == [x["id"] for x in rows]
    for x in all_jsonl:
        y = by_id[x["id"]]
        assert all(x[k] == v for k,v in y.items())
        assert x["as_of_year"] == y["target_year"]
        assert x["gold_answer"] == y["ground_truth_answer"]
        assert x["gold_doc_id"] == y["source_doc_id"]
        assert x["outdated_answer"] == y["outdated_trap_answer"]
        assert x["type"] == y["category"]
    for category, filename in (("active_rule", "valid"),
                              ("superseded_rule", "superseded"),
                              ("temporal_specific", "year_specific")):
        assert _jsonl("data/qa_benchmark/" + filename + ".jsonl") == [
            x for x in rows if x["category"] == category
        ]


def test_all_42_corrections_are_source_anchored_and_sha_matches():
    rows = {r["id"]:r for r in _load("data/benchmark/uet_regulation_benchmark.json")}
    assert len(CORRECTED) == len(SOURCE_ANCHORS) == 42
    assert set(CORRECTED) == set(SOURCE_ANCHORS)
    source_paths = sorted((ROOT / "data/raw/uet/markdown").rglob("*.md"))
    by_hash = {hashlib.sha256(p.read_bytes()).hexdigest():p for p in source_paths}
    for id in CORRECTED:
        row = rows[id]
        assert row["source_sha256"] in by_hash, id
        text = by_hash[row["source_sha256"]].read_text(encoding="utf-8").casefold()
        for anchor in SOURCE_ANCHORS[id]:
            assert anchor.casefold() in text, (id, anchor)


def test_new_gold_does_not_repeat_disproved_core_claims():
    rows = {r["id"]:r for r in _load("data/benchmark/uet_regulation_benchmark.json")}
    wrong = {
        "BENCH_SUP_017": ["12/04/2024", "25/03/2024"],
        "BENCH_SUP_018": ["30/03/2025", "04/2025"],
        "BENCH_TEM_019": ["15/01/2026", "30/03/2026"],
        "BENCH_ACT_017": ["14 tín chỉ"],
        "BENCH_ACT_020": ["3968/QĐ"],
        "BENCH_SUP_016": ["2928/QĐ"],
        "BENCH_TEM_016": ["2.400.000"],
        "BENCH_TEM_022": ["01/09/2026"],
    }
    for id, phrases in wrong.items():
        gold = rows[id]["ground_truth_answer"]
        for phrase in phrases:
            assert phrase not in gold, (id, phrase)


def test_original_48_unedited_rows_are_bitwise_semantically_unchanged():
    rows = _load("data/benchmark/uet_regulation_benchmark.json")
    untouched = [r for r in rows if r["id"] not in set(CORRECTED)]
    assert len(untouched) == 48
    digest = hashlib.sha256(json.dumps(untouched, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == UNCHANGED_48_DIGEST
