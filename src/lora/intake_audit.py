"""Offline input audit for ChronoReg continual LoRA.

A syntactically approved row is not necessarily human-reviewed or a useful
instruction-answer pair. This gate deliberately blocks identifiable generated
placeholder answers and non-human reviewer attestations. It does not claim to
perform semantic fact checking or certify a held-out benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .contracts import read_jsonl, sha256

TEMPLATE_ANSWER = 'căn cứ theo văn bản quy định của trường đại học công nghệ áp dụng trong năm học'
AUTO_REVIEWERS = {'antigravity qa reviewer', 'ai reviewer', 'automated reviewer', 'auto reviewer'}
YEAR_RANGE = range(2022, 2027)
SPLITS = {'active_rule': 'valid.jsonl', 'superseded_rule': 'superseded.jsonl',
          'temporal_specific': 'year_specific.jsonl'}


def _normalize(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def classify_qa(row: dict) -> list[str]:
    """High-confidence invalid-approval signals, not semantic truth labels."""
    flags = []
    reviewer = _normalize(str(row.get('reviewer') or ''))
    if reviewer in AUTO_REVIEWERS or reviewer.startswith(('ai agent ', 'llm ')):
        flags.append('AUTOMATED_REVIEWER')
    answer = _normalize(str(row.get('answer') or ''))
    if answer.startswith(TEMPLATE_ANSWER) and 'nội dung được quy định như sau' in answer:
        flags.append('TEMPLATE_NONANSWER')
    q = _normalize(str(row.get('question') or ''))
    if ('nội dung về ' in q and 'được quy định cụ thể như thế nào' in q
            or 'quy chế của uet hướng dẫn chi tiết điều khoản về' in q
            or 'quy định năm học' in q and 'nêu rõ những nội dung gì liên quan đến' in q):
        flags.append('GENERIC_QUESTION')
    return flags


def ensure_curated(rows: list[dict]) -> None:
    """Block known fabricated approvals before writing a prepared training set."""
    bad = [(str(r.get('id', '?')), classify_qa(r)) for r in rows]
    blockers = [(ident, f) for ident, f in bad
                if 'AUTOMATED_REVIEWER' in f or 'TEMPLATE_NONANSWER' in f]
    if blockers:
        totals = Counter(flag for _, flags in blockers for flag in flags)
        raise ValueError(
            f'LoRA training blocked: {len(blockers)} rows have non-human review '
            f'attestations or template non-answers ({dict(totals)}); '
            'replace with independently reviewed, fact-specific QA. '
            f'First affected ID: {blockers[0][0]}')


def _all_benchmark_source_hashes(repo: Path) -> dict[str, set[str]]:
    """Allow more than one file for a hash; do not infer legal effectivity."""
    matches: dict[str, set[str]] = {}
    root = repo / 'data/raw/uet/markdown'
    if root.is_dir():
        for file in root.rglob('*.md'):
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            matches.setdefault(digest, set()).add(file.relative_to(repo).as_posix())
    return matches


def audit(repo: Path, train_file: Path, benchmark_file: Path,
          prepared_dir: Path) -> tuple[dict, list[dict]]:
    repo = repo.resolve()
    train = read_jsonl(train_file)
    bench = read_jsonl(benchmark_file)
    cases = []
    for row in train:
        flags = classify_qa(row)
        source = repo / str(row.get('source_file', ''))
        if not source.is_file() or not source.resolve().is_relative_to(repo):
            flags.append('SOURCE_MISSING_OR_UNSAFE')
        else:
            contents = source.read_bytes()
            if hashlib.sha256(contents).hexdigest() != row.get('source_sha256'):
                flags.append('SOURCE_HASH_MISMATCH')
            try:
                if row.get('evidence_quote') not in contents.decode('utf-8-sig'):
                    flags.append('EVIDENCE_NOT_IN_SOURCE')
            except (UnicodeError, TypeError):
                flags.append('EVIDENCE_NOT_IN_SOURCE')
        cases.append({'id': row.get('id'), 'year': row.get('as_of_year'),
                      'flags': flags, 'reviewer': row.get('reviewer'),
                      'source_file': row.get('source_file')})
    critical_flags = {'AUTOMATED_REVIEWER', 'TEMPLATE_NONANSWER', 'SOURCE_MISSING_OR_UNSAFE',
                      'SOURCE_HASH_MISMATCH', 'EVIDENCE_NOT_IN_SOURCE'}
    flags_count = Counter(f for item in cases for f in item['flags'])
    src_index = _all_benchmark_source_hashes(repo)
    missing_bench_src = [r.get('id') for r in bench if r.get('source_sha256') not in src_index]
    benchmark_errors = []
    if len({r.get('id') for r in bench}) != len(bench):
        benchmark_errors.append('BENCHMARK_DUPLICATE_ID')
    if len({_normalize(str(r.get('question', ''))) for r in bench}) != len(bench):
        benchmark_errors.append('BENCHMARK_DUPLICATE_QUESTION')
    for kind, split_file in SPLITS.items():
        path = benchmark_file.parent / split_file
        if not path.is_file():
            benchmark_errors.append(f'SPLIT_MISSING:{split_file}')
            continue
        split = read_jsonl(path)
        ids = {r.get('id') for r in bench if r.get('type') == kind}
        if {r.get('id') for r in split} != ids or len(split) != len(ids):
            benchmark_errors.append(f'SPLIT_INCONSISTENT:{split_file}')
    aliases = repo / 'data/benchmark/uet_regulation_benchmark.json'
    if aliases.is_file():
        primary = json.loads(aliases.read_text(encoding='utf-8'))
        if not isinstance(primary, list) or len(primary) != len(bench):
            benchmark_errors.append('BENCHMARK_CANONICAL_COUNT_MISMATCH')
        else:
            lookup = {r.get('id'): r for r in bench}
            for r in primary:
                other = lookup.get(r.get('id'))
                if other is None or any(other.get(k) != v for k, v in r.items()):
                    benchmark_errors.append('BENCHMARK_CANONICAL_CONTENT_MISMATCH')
                    break
    manifest_path = prepared_dir / 'manifest.json'
    manifest_checks = {'present': manifest_path.is_file(),
                       'train_source_sha_matches': False, 'benchmark_sha_matches': False,
                       'year_shas_match': {}, 'year_counts_match': {}}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest_checks['train_source_sha_matches'] = manifest.get('train_sha256') == sha256(train_file)
        manifest_checks['benchmark_sha_matches'] = manifest.get('benchmark_sha256') == sha256(benchmark_file)
        for y in YEAR_RANGE:
            path = prepared_dir / f'train_{y}.jsonl'
            manifest_checks['year_shas_match'][str(y)] = (
                path.is_file() and manifest.get('year_sha256', {}).get(str(y)) == sha256(path))
            manifest_checks['year_counts_match'][str(y)] = (
                path.is_file() and len(read_jsonl(path)) == manifest.get('counts', {}).get(str(y)))
    stage_ok = (manifest_checks['present'] and manifest_checks['train_source_sha_matches']
                and manifest_checks['benchmark_sha_matches']
                and len(manifest_checks['year_shas_match']) == len(YEAR_RANGE)
                and all(manifest_checks['year_shas_match'].values())
                and all(manifest_checks['year_counts_match'].values()))
    blocking_ids = [c['id'] for c in cases if critical_flags.intersection(c['flags'])]
    if missing_bench_src:
        benchmark_errors.append('BENCHMARK_SOURCE_SHA_NOT_FOUND')
    report = {
        'status': 'READY_FOR_HUMAN_REVIEW_ONLY' if not blocking_ids and stage_ok and not benchmark_errors
                  else 'BLOCKED_FOR_TRAINING',
        'semantic_truth_verified': False,
        'human_approval_verified': False,
        'heldout_semantic_isolation_verified': False,
        'train': {'count': len(train), 'by_year': dict(sorted(Counter(str(r.get('as_of_year')) for r in train).items())),
                  'flag_counts': dict(sorted(flags_count.items())), 'blocking_rows': len(blocking_ids),
                  'example_blocking_ids': blocking_ids[:12]},
        'benchmark': {'count': len(bench), 'by_type': dict(sorted(Counter(str(r.get('type')) for r in bench).items())),
                      'by_year': dict(sorted(Counter(str(r.get('as_of_year')) for r in bench).items())),
                      'missing_source_ids': missing_bench_src[:12], 'structural_errors': benchmark_errors,
                      'same_document_ids_as_train': len({r.get('gold_doc_id') for r in bench} &
                                                        {r.get('doc_id') for r in train})},
        'prepared_manifest': manifest_checks,
        'notes': [
            'Hash agreement proves file integrity, not factual correctness or independent human approval.',
            'Train/benchmark sharing source documents is not necessarily leakage, but overlapping facts must be reviewed.',
            'Passing structural QA checks does not establish answer quality or catastrophic-forgetting performance.',
        ],
    }
    return report, cases


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description='Audit LoRA intake without modifying existing datasets')
    p.add_argument('--repo', type=Path, default=Path('.'))
    p.add_argument('--train', type=Path, default=Path('src/lora/runs/approved_qa.jsonl'))
    p.add_argument('--benchmark', type=Path, default=Path('data/qa_benchmark/benchmark.jsonl'))
    p.add_argument('--prepared', type=Path, default=Path('src/lora/runs/prepared'))
    p.add_argument('--report', type=Path, default=None)
    p.add_argument('--cases', type=Path, default=None)
    p.add_argument('--require-ready', action='store_true', help='Return nonzero if blocked')
    args = p.parse_args(argv)
    repo = args.repo.resolve()
    resolve = lambda path: path if path.is_absolute() else repo / path
    report, cases = audit(repo, resolve(args.train), resolve(args.benchmark), resolve(args.prepared))
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    print(output, end='')
    for path, data in ((args.report, output),
                       (args.cases, ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n'
                                          for row in cases))):
        if path is not None:
            dest = resolve(path)
            if dest.exists():
                raise FileExistsError(f'Refusing to overwrite existing audit: {dest}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(data, encoding='utf-8')
    if args.require_ready and report['status'] != 'READY_FOR_HUMAN_REVIEW_ONLY':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
