"""Read-only quality triage for table-derived QA drafts.

This audit does NOT accept/reject candidates or certify the underlying rules.
It validates current SHA-bound provenance and creates a CSV for manual review.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from .contracts import question_key, read_jsonl, validate_benchmark
from .review import _read_candidates
from .table_candidates import IDENTIFIER_COLUMNS, _amount

_COLUMNS = (
    'candidate_id', 'year', 'doc_id', 'source_file', 'candidate_sha256',
    'table_section', 'table_row_label', 'table_column', 'draft_question',
    'draft_answer', 'evidence_quote', 'risk_flags', 'review_action',
)


def _safe_csv(value: object) -> str:
    """Protect reviewers who open the report in spreadsheet software."""
    text = str(value)
    if text and text.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + text
    return text


def audit_tables(repo: Path, candidates: Path, registry: Path, holds: Path,
                 output: Path, benchmark: Path | None = None) -> dict:
    """Validate sources, flag suspect drafts, and write a non-overwriting worklist.

    Exact overlap/high lexical similarity are review signals, never an assertion
    that semantic leakage is absent. A team-approved frozen benchmark is still
    required before training.
    """
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite existing table audit: {output}')
    if output.resolve() in {candidates.resolve(), registry.resolve(), holds.resolve()}:
        raise ValueError('Audit output may not replace an input file')
    rows = _read_candidates(repo, candidates, registry, holds)
    bench = validate_benchmark(read_jsonl(benchmark)) if benchmark else []
    if benchmark is not None and not bench:
        raise ValueError('Explicit held-out benchmark is empty')
    bench_keys = {question_key(b['question']) for b in bench}
    bench_by_doc = {}
    for b in bench:
        bench_by_doc.setdefault(b['gold_doc_id'], []).append(question_key(b['question']))
    counts = Counter()
    years = Counter()
    work = []
    for row in rows:
        flags = []
        answer = row.get('answer', '')
        column = row.get('table_column', '')
        section = row.get('table_section', '')
        if not isinstance(answer, str) or not _amount(answer):
            flags.append('NON_MONETARY_VALUE')
        if not isinstance(column, str) or column.strip().casefold() in IDENTIFIER_COLUMNS:
            flags.append('IDENTIFIER_COLUMN')
        if (not isinstance(section, str) or not section.strip() or
                'quyết định:' in section.casefold()):
            flags.append('GENERIC_SECTION')
        qkey = question_key(row['question'])
        if benchmark is not None:
            if qkey in bench_keys:
                flags.append('BENCHMARK_EXACT_QUESTION')
            elif any(SequenceMatcher(None, qkey, bq).ratio() >= 0.88
                     for bq in bench_by_doc.get(row['doc_id'], [])):
                flags.append('BENCHMARK_SIMILAR_QUESTION')
        if not flags:
            flags.append('SOURCE_PDF_REVIEW_REQUIRED')
        for flag in flags:
            counts[flag] += 1
        years[row['as_of_year']] += 1
        action = ('HOLD_FOR_REWRITE' if any(f in flags for f in (
            'NON_MONETARY_VALUE', 'IDENTIFIER_COLUMN', 'GENERIC_SECTION',
            'BENCHMARK_EXACT_QUESTION', 'BENCHMARK_SIMILAR_QUESTION'))
                  else 'CHECK_ORIGINAL_PDF_AND_AMENDMENTS')
        from .review import candidate_fingerprint
        work.append({
            'candidate_id': row['id'], 'year': row['as_of_year'],
            'doc_id': row['doc_id'], 'source_file': row['source_file'],
            'candidate_sha256': candidate_fingerprint(row),
            'table_section': section, 'table_row_label': row.get('table_row_label', ''),
            'table_column': column, 'draft_question': row['question'],
            'draft_answer': answer, 'evidence_quote': row['evidence_quote'],
            'risk_flags': ';'.join(flags), 'review_action': action,
        })
    # Prepare all data before creating a new output; never modify review decisions.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        for r in work:
            writer.writerow({key: _safe_csv(r[key]) for key in _COLUMNS})
    return {
        'audited_candidates': len(rows), 'source_documents': len({r['doc_id'] for r in rows}),
        'years': {str(y): years[y] for y in range(2022, 2027)},
        'flags': dict(sorted(counts.items())),
        'requires_rewrite': sum(r['review_action'] == 'HOLD_FOR_REWRITE' for r in work),
        'approved': 0, 'benchmark_provided': benchmark is not None,
        'benchmark_separation_not_certified': True,
        'output': str(output),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Audit DRAFT-only table QA for human review')
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--candidates', type=Path, default=Path('src/lora/runs/table_candidates.jsonl'))
    parser.add_argument('--registry', type=Path, default=Path('data/versioning/documents.jsonl'))
    parser.add_argument('--holds', type=Path, default=Path('data/versioning/publication_holds.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('src/lora/runs/table_quality_audit.csv'))
    parser.add_argument('--benchmark', type=Path, help='Optional frozen held-out benchmark, read only')
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    def resolve(p: Path) -> Path:
        return p if p.is_absolute() else root / p
    print(json.dumps(audit_tables(root, resolve(args.candidates), resolve(args.registry),
                                  resolve(args.holds), resolve(args.output),
                                  resolve(args.benchmark) if args.benchmark else None),
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
