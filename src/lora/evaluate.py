"""Evaluate held-out old-year questions after each LoRA update.

This is diagnostic forgetting analysis, NOT the team's version accuracy scorer.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .contracts import validate_benchmark, read_jsonl, write_jsonl
from .metrics import forgetting, score_predictions


def evaluate_stages(benchmark: Path, years: list[int],
                    predict: Callable[[int, str, int], str], output: Path) -> dict:
    rows = validate_benchmark(read_jsonl(benchmark))
    scores = {}
    all_predictions = []
    for stage in years:
        by_year = defaultdict(list)
        for q in rows:
            if q['as_of_year'] > stage:
                continue  # Future-year questions are ineligible at this checkpoint.
            predicted = predict(stage, q['question'], q['as_of_year'])
            scored = {'id': q['id'], 'question': q['question'],
                      'gold_answer': q['gold_answer'], 'gold_doc_id': q['gold_doc_id'],
                      'outdated_answer': q.get('outdated_answer'),
                      'type': q['type'], 'as_of_year': q['as_of_year'],
                      'checkpoint_year': stage, 'prediction': predicted}
            by_year[q['as_of_year']].append(scored)
            all_predictions.append(scored)
        scores[stage] = {year: score_predictions(items)['exact_match'] for year, items in by_year.items()}
    summary = {'year_convention': 'academic_year_start',
               'held_out_exact_match_by_checkpoint': {str(y): {str(t): v for t, v in xs.items()}
                                                        for y, xs in scores.items()},
               'forgetting_exact_match_drop': forgetting(scores),
               'count': len(all_predictions),
               'note': 'Exact-match forgetting diagnostics; src/eval is responsible for version accuracy and semantic outdated-answer rate.'}
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / 'predictions.jsonl', all_predictions)
    (output / 'forgetting_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    return summary
