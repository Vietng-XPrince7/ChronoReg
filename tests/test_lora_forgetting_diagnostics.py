"""Offline regression tests for continuous-year LoRA forgetting diagnostics."""
import json

import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.evaluate import evaluate_stages
from src.lora.metrics import token_f1


def make_bench(year, suffix, gold):
    return dict(id=f'b-{suffix}', question=f'Question {suffix}?', gold_answer=gold,
                gold_doc_id=f'doc-{suffix}', as_of_year=year,
                type='temporal_specific', outdated_answer='old answer')


def test_reports_token_f1_forgetting_when_exact_match_is_always_zero(tmp_path):
    bench = tmp_path / 'bench.jsonl'
    write_jsonl(bench, [make_bench(2022, 'old', 'học phí 2 triệu đồng'),
                        make_bench(2023, 'new', 'học bổng 3 triệu')])
    predictions = {
        (2022, 2022): 'học phí 2 triệu',
        (2023, 2022): 'học phí',
        (2023, 2023): 'học bổng',
    }
    called = []
    def predict(stage, question, year):
        called.append((stage, year))
        return predictions[(stage, year)]
    result = evaluate_stages(bench, [2022, 2023], predict, tmp_path / 'eval')
    assert called == [(2022, 2022), (2023, 2022), (2023, 2023)]
    assert result['held_out_exact_match_by_checkpoint']['2022']['2022'] == 0.0
    assert result['forgetting_exact_match_drop']['2023']['2022'] == 0.0
    assert result['forgetting_token_f1_drop']['2023']['2022'] > 0.2
    assert result['mean_forgetting_token_f1']['2022'] is None
    assert result['mean_forgetting_token_f1']['2023'] == pytest.approx(
        result['forgetting_token_f1_drop']['2023']['2022'])
    assert result['held_out_count_by_checkpoint'] == {'2022': {'2022': 1},
                                                      '2023': {'2022': 1, '2023': 1}}
    assert result['unique_benchmark_cases'] == 2
    assert result['count'] == 3
    assert len(read_jsonl(tmp_path / 'eval/predictions.jsonl')) == 3
    assert json.loads((tmp_path / 'eval/forgetting_summary.json').read_text()) == result


def test_per_case_scores_preserve_provenance(tmp_path):
    bench = tmp_path / 'bench.jsonl'
    write_jsonl(bench, [make_bench(2025, 'k', '8% học phí học kỳ')])
    result = evaluate_stages(bench, [2025], lambda *_: '8% học phí', tmp_path / 'out')
    row = read_jsonl(tmp_path / 'out/predictions.jsonl')[0]
    assert row['gold_doc_id'] == 'doc-k'
    assert row['checkpoint_year'] == 2025
    assert row['exact_match'] == 0
    assert row['token_f1'] == pytest.approx(token_f1('8% học phí', '8% học phí học kỳ'))
    assert result['forgetting_token_f1_drop']['2025'] == {}


@pytest.mark.parametrize('years', [[], [2023, 2022], [2023, 2023]])
def test_reject_invalid_year_sequence_before_output(tmp_path, years):
    bench = tmp_path / 'bench.jsonl'
    write_jsonl(bench, [make_bench(2022, 'x', 'answer')])
    with pytest.raises(ValueError, match='sorted, unique and nonempty'):
        evaluate_stages(bench, years, lambda *_: 'answer', tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_reject_nontext_prediction_before_output(tmp_path):
    bench = tmp_path / 'bench.jsonl'
    write_jsonl(bench, [make_bench(2022, 'x', 'answer')])
    with pytest.raises(TypeError, match='prediction must be text'):
        evaluate_stages(bench, [2022], lambda *_: None, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_empty_benchmark_does_not_report_zero_accuracy(tmp_path):
    bench = tmp_path / 'bench.jsonl'
    bench.write_text('', encoding='utf8')
    with pytest.raises(ValueError, match='empty'):
        evaluate_stages(bench, [2022], lambda *_: '', tmp_path / 'out')
    assert not (tmp_path / 'out').exists()
