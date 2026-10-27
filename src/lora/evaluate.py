"""Evaluate historical held-out questions after each sequential LoRA stage.

Diagnostics for the LoRA experiment, not the team's version-accuracy scorer.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .contracts import validate_benchmark, read_jsonl, write_jsonl
from .metrics import forgetting, normalize, score_predictions, token_f1


def _string_years(history: dict[int, dict[int, float]]) -> dict[str, dict[str, float]]:
    return {str(stage): {str(year): value for year, value in per_year.items()}
            for stage, per_year in history.items()}


def _mean_forgetting(drops: dict[str, dict[str, float]]) -> dict[str, float | None]:
    """Macro-average across prior years. First checkpoint has no earlier year."""
    return {stage: (sum(values.values()) / len(values) if values else None)
            for stage, values in drops.items()}


def evaluate_stages(benchmark: Path, years: list[int],
                    predict: Callable[[int, str, int], str], output: Path) -> dict:
    """Assess all available past-year tasks without peeking at future years.

    Evaluate the same heldout items after each checkpoint. The benchmark must
    be independently frozen; these numbers must not drive training selection.
    """
    if not years or years != sorted(set(years)):
        raise ValueError('Checkpoint years must be sorted, unique and nonempty')
    rows = validate_benchmark(read_jsonl(benchmark))
    if not rows:
        raise ValueError('Held-out benchmark is empty')

    exact_scores: dict[int, dict[int, float]] = {}
    f1_scores: dict[int, dict[int, float]] = {}
    sample_counts: dict[int, dict[int, int]] = {}
    all_predictions: list[dict] = []
    for stage in years:
        by_year = defaultdict(list)
        for q in rows:
            if q['as_of_year'] > stage:
                continue  # Future-year questions are ineligible at this checkpoint.
            predicted = predict(stage, q['question'], q['as_of_year'])
            if not isinstance(predicted, str):
                raise TypeError(f"Checkpoint {stage}, {q['id']}: prediction must be text")
            scored = {'id': q['id'], 'question': q['question'],
                      'gold_answer': q['gold_answer'], 'gold_doc_id': q['gold_doc_id'],
                      'outdated_answer': q.get('outdated_answer'),
                      'type': q['type'], 'as_of_year': q['as_of_year'],
                      'checkpoint_year': stage, 'prediction': predicted,
                      'exact_match': int(normalize(predicted) == normalize(q['gold_answer'])),
                      'token_f1': token_f1(predicted, q['gold_answer'])}
            by_year[q['as_of_year']].append(scored)
            all_predictions.append(scored)
        scores = {year: score_predictions(items) for year, items in by_year.items()}
        exact_scores[stage] = {year: result['exact_match'] for year, result in scores.items()}
        f1_scores[stage] = {year: result['token_f1'] for year, result in scores.items()}
        sample_counts[stage] = {year: result['count'] for year, result in scores.items()}

    drops_em = forgetting(exact_scores)
    drops_f1 = forgetting(f1_scores)
    summary = {
        'year_convention': 'academic_year_start',
        'held_out_exact_match_by_checkpoint': _string_years(exact_scores),
        'held_out_token_f1_by_checkpoint': _string_years(f1_scores),
        'held_out_count_by_checkpoint': _string_years(sample_counts),
        'forgetting_exact_match_drop': drops_em,
        'forgetting_token_f1_drop': drops_f1,
        'mean_forgetting_exact_match': _mean_forgetting(drops_em),
        'mean_forgetting_token_f1': _mean_forgetting(drops_f1),
        'count': len(all_predictions),
        'unique_benchmark_cases': len(rows),
        'note': ('Exact-match and whitespace-token-F1 forgetting are automatic string '
                 'diagnostics only. Similar wording can score well with wrong numbers; '
                 'paraphrases can score poorly. The team src/eval module owns version '
                 'accuracy and semantic outdated-answer metrics. Do not select '
                 'checkpoints or hyperparameters by held-out test performance.'),
    }
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / 'predictions.jsonl', all_predictions)
    (output / 'forgetting_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    return summary
