"""Regression tests for retrospective held-out cohorts and per-case forgetting."""
from pathlib import Path
import json
import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.evaluate import evaluate_stages


def item(year, name, answer='correct', subject=None):
    row = dict(id=name, question=f'Question {name}', gold_answer=answer,
               gold_doc_id=f'source-{name}', as_of_year=year,
               type='temporal_specific')
    if subject is not None:
        row['retrospective_subject_year'] = subject
    return row


def test_retrospective_case_never_appears_before_available_checkpoint(tmp_path):
    bench = tmp_path / 'bench.jsonl'
    write_jsonl(bench, [item(2025, 'ordinary'), item(2026, 'retrospective', subject=2025)])
    invocations = []
    def predict(stage, question, year):
        invocations.append((stage, question, year))
        return 'correct'
    result = evaluate_stages(bench, [2025, 2026], predict, tmp_path / 'eval')
    assert invocations == [(2025, 'Question ordinary', 2025),
                           (2026, 'Question ordinary', 2025),
                           (2026, 'Question retrospective', 2026)]
    by_stage = read_jsonl(tmp_path / 'eval/predictions.jsonl')
    retrospective = [x for x in by_stage if x['id'] == 'retrospective']
    assert len(retrospective) == 1
    assert retrospective[0]['checkpoint_year'] == 2026
    assert retrospective[0]['retrospective_subject_year'] == 2025
    assert retrospective[0]['first_eligible_year'] == 2026
    assert result['policy_subject_count_by_checkpoint']['2025'] == {'2025': 1}
    assert result['policy_subject_count_by_checkpoint']['2026'] == {'2025': 2}
    assert result['case_stable_forgetting_comparable_counts']['2026'] == {'2025': 1}


def test_per_case_forgetting_not_contaminated_by_new_item(tmp_path):
    bench = tmp_path / 'bench.jsonl'
    write_jsonl(bench, [item(2022, 'original'), item(2024, 'later', subject=2022)])
    answers = {
        (2022, 'original'): 'correct',
        (2023, 'original'): 'correct',
        (2024, 'original'): 'wrong',
        (2024, 'later'): 'wrong',
        (2025, 'original'): 'wrong',
        (2025, 'later'): 'correct',
    }
    def predict(stage, question, year):
        return answers[(stage, question.replace('Question ', ''))]
    result = evaluate_stages(bench, [2022, 2023, 2024, 2025], predict, tmp_path / 'out')
    counts = result['case_stable_forgetting_comparable_counts']
    assert counts['2024']['2022'] == 1  # Later item has no preceding observation
    assert counts['2025']['2022'] == 2  # Both items now have a baseline
    drops = result['case_stable_forgetting_exact_match_by_subject_year']
    assert drops['2024']['2022'] == 1.0  # Only original item forgot
    assert drops['2025']['2022'] == 0.5  # Original forgot, later improved
    # Legacy availability-year grouping remains for backwards compatibility.
    assert result['held_out_count_by_checkpoint']['2024'] == {'2022': 1, '2024': 1}


def test_invalid_retrospective_year_rejected_before_inference(tmp_path):
    bench = tmp_path / 'b.jsonl'
    for bad in (2026, '2023', True, 2021):
        row = item(2024, 'invalid', subject=bad)
        write_jsonl(bench, [row])
        out = tmp_path / 'invalid'
        with pytest.raises(ValueError, match='retrospective_subject_year'):
            evaluate_stages(bench, [2024], lambda *_: (_ for _ in ()).throw(AssertionError()), out)
        assert not out.exists()


def test_original_cases_still_have_equal_subject_and_availability(tmp_path):
    bench = tmp_path / 'b.jsonl'
    write_jsonl(bench, [item(2022, 'simple')])
    result = evaluate_stages(bench, [2022, 2023], lambda *_: 'correct', tmp_path / 'out')
    assert result['case_stable_forgetting_comparable_counts']['2022'] == {}
    assert result['case_stable_forgetting_comparable_counts']['2023'] == {'2022': 1}
    assert result['case_stable_forgetting_token_f1_by_subject_year']['2023']['2022'] == 0.0
    assert json.loads((tmp_path / 'out/forgetting_summary.json').read_text(encoding='utf-8')) == result


def test_actual_v8_90_cases_are_not_exposed_before_2026(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'docs' / 'benchmark_review_v8' / 'review_only' / 'benchmark_candidate_90_NOT_FROZEN.jsonl'
    if not source.is_file():
        pytest.skip('Optional V8 review snapshot is not present')
    rows = read_jsonl(source)
    assert len(rows) == 90
    candidates = {r['id'] for r in rows if r.get('retrospective_subject_year') is not None}
    assert candidates == {'BENCH_SUP_001', 'BENCH_SUP_002', 'BENCH_SUP_003',
                          'BENCH_SUP_004', 'BENCH_SUP_011', 'BENCH_SUP_021'}
    result = evaluate_stages(source, [2022,2023,2024,2025,2026], lambda *_: '', tmp_path / 'out')
    by_stage = read_jsonl(tmp_path / 'out/predictions.jsonl')
    for row in by_stage:
        if row['id'] in candidates:
            assert row['checkpoint_year'] == 2026
    assert result['unique_benchmark_cases'] == 90
