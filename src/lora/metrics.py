"""Transparent held-out diagnostic metrics, not a replacement for team eval."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter


def normalize(text: str) -> str:
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold()))


def token_f1(predicted: str, gold: str) -> float:
    p, g = normalize(predicted).split(), normalize(gold).split()
    if not p or not g:
        return float(not p and not g)
    common = sum((Counter(p) & Counter(g)).values())
    if not common:
        return 0.0
    precision, recall = common / len(p), common / len(g)
    return 2 * precision * recall / (precision + recall)


def score_predictions(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError('No predictions to score')
    exact = sum(normalize(r['prediction']) == normalize(r['gold_answer']) for r in rows)
    # Equality to an outdated answer is ONLY an exact-match proxy, never a legal verdict.
    outdated = 0
    denom = 0
    for row in rows:
        values = row.get('outdated_answer')
        if isinstance(values, str):
            values = [values]
        if values is not None:
            denom += 1
            if normalize(row['prediction']) in {normalize(x) for x in values if isinstance(x, str)}:
                outdated += 1
    return {'count': len(rows), 'exact_match': exact / len(rows),
            'token_f1': sum(token_f1(r['prediction'], r['gold_answer']) for r in rows) / len(rows),
            'outdated_exact_proxy': (outdated / denom if denom else None),
            'outdated_proxy_denominator': denom,
            'caveat': 'Diagnostic string metrics only; team src/eval owns version accuracy and semantic outdated-answer rate.'}


def forgetting(history: dict[int, dict[int, float]]) -> dict[str, dict[str, float]]:
    """history[checkpoint_year][test_year] = held-out score; larger is better.

    Uses best score from first exposure through current stage, excluding future years.
    """
    result = {}
    for current in sorted(history):
        per_year = {}
        for year in sorted(y for y in history[current] if y < current):
            prior = [scores[year] for stage, scores in history.items()
                     if year <= stage < current and year in scores]
            if prior:
                per_year[str(year)] = max(0.0, max(prior) - history[current][year])
        result[str(current)] = per_year
    return result
