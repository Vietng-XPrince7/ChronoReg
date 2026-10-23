"""Validate approved QA, reject benchmark leakage, stage chronological training sets."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from .contracts import (read_jsonl, sha256, validate_benchmark,
                        validate_training, write_jsonl)


def prepare(repo: Path, train_path: Path, benchmark_path: Path,
            output_dir: Path, years: list[int]) -> dict:
    train_raw = read_jsonl(train_path)
    benchmark = validate_benchmark(read_jsonl(benchmark_path))
    if not benchmark:
        raise ValueError('Held-out benchmark is empty. Request the validated benchmark from the data/eval owner.')
    training = validate_training(train_raw, repo, benchmark)
    known = set(years)
    if len(known) != len(years) or years != sorted(years) or any(y not in range(2022, 2027) for y in years):
        raise ValueError('years must be sorted, unique, in [2022, 2026]')
    extras = sorted(set(row['as_of_year'] for row in training) - known)
    if extras:
        raise ValueError(f'Approved QA exists outside the requested years: {extras}')
    # Fail rather than silently skipping a training stage in a continual experiment.
    counts = Counter(r['as_of_year'] for r in training)
    missing = [y for y in years if not counts[y]]
    if missing:
        raise ValueError(f'No approved training QA for stage years: {missing}')
    # Compare benchmark question + document evidence, not only row IDs.
    bench_doc_question = {(r['gold_doc_id'], r['question'].strip().casefold()) for r in benchmark}
    if any((r['doc_id'], r['question'].strip().casefold()) in bench_doc_question for r in training):
        raise ValueError('Benchmark question/document overlaps training')
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'train_sha256': sha256(train_path),
        'benchmark_sha256': sha256(benchmark_path),
        'year_convention': 'academic_year_start',
        'years': years,
        'counts': {str(y): counts[y] for y in years},
        'year_sha256': {},
        'total': len(training),
        'no_future_data': True,
        'held_out_questions_excluded': True,
    }
    for y in years:
        stage_path = output_dir / f'train_{y}.jsonl'
        write_jsonl(stage_path, [r for r in training if r['as_of_year'] == y])
        manifest['year_sha256'][str(y)] = sha256(stage_path)
    (output_dir / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    return manifest
