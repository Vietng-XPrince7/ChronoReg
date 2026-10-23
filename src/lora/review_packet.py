"""Non-approving review worklist combining prose and table QA drafts.

All candidates must pass SHA/document/hold verification. This tool never edits
review decisions, marks drafts approved, or exports training data. An optional
team-owned benchmark is used only for overlap signals, never copied to output.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from .contracts import question_key, read_jsonl, sha256, validate_benchmark
from .review import _read_candidates, candidate_fingerprint
from .table_candidates import IDENTIFIER_COLUMNS, _amount

FIELDS = (
    'priority', 'source_kind', 'academic_year', 'candidate_id', 'candidate_sha256',
    'doc_id', 'source_file', 'source_sha256', 'risk_flags', 'review_action',
    'question_draft', 'answer_draft', 'section', 'row_label', 'column',
    'evidence_quote', 'human_decision', 'reviewer', 'review_notes',
)


def _excel_safe(value: object) -> str:
    """Do not allow Markdown-derived values to execute as CSV formulas."""
    text = '' if value is None else str(value)
    if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + text
    return text


def generate_packet(repo: Path, prose: Path, tables: Path, registry: Path,
                    holds: Path, output: Path, manifest: Path,
                    benchmark: Path | None = None) -> dict:
    repo = repo.resolve()
    inputs = [prose, tables, registry, holds] + ([benchmark] if benchmark else [])
    protected = {p.resolve() for p in inputs}
    if prose.resolve() == tables.resolve():
        raise ValueError('Prose and table candidate paths must be different')
    if output.resolve() == manifest.resolve() or any(
            p.resolve() in protected for p in (output, manifest)):
        raise ValueError('Output must not replace an input or each other')
    if output.exists() or manifest.exists():
        raise FileExistsError('Review packet already exists. Existing human work will not be overwritten')
    prose_rows = _read_candidates(repo, prose, registry, holds)
    table_rows = _read_candidates(repo, tables, registry, holds)
    if not prose_rows and not table_rows:
        raise ValueError('No candidates available for manual review')
    all_rows = [('paragraph', r) for r in prose_rows] + [('table', r) for r in table_rows]
    ids = [r['id'] for _, r in all_rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate candidate IDs across candidate files')
    bench_rows = validate_benchmark(read_jsonl(benchmark)) if benchmark else []
    if benchmark is not None and not bench_rows:
        raise ValueError('Explicit benchmark is empty')
    benchmark_questions = {question_key(b['question']) for b in bench_rows}
    benchmark_doc_questions = defaultdict(list)
    for b in bench_rows:
        benchmark_doc_questions[b['gold_doc_id']].append(question_key(b['question']))
    draft_questions = Counter(question_key(r['question']) for _, r in all_rows)
    report_rows = []
    flag_counts = Counter()
    year_counts = Counter()
    priorities = Counter()
    for kind, row in all_rows:
        flags = []
        qkey = question_key(row['question'])
        if draft_questions[qkey] > 1:
            flags.append('DUPLICATE_DRAFT_QUESTION')
        if kind == 'paragraph':
            flags.append('GENERIC_PARAGRAPH_DRAFT')
        else:
            col = str(row.get('table_column', '')).strip().casefold()
            section = str(row.get('table_section', '')).strip()
            if col in IDENTIFIER_COLUMNS or not col:
                flags.append('IDENTIFIER_COLUMN')
            if not _amount(str(row.get('answer', ''))):
                flags.append('NON_MONETARY_VALUE')
            if not section or 'quyết định:' in section.casefold():
                flags.append('GENERIC_SECTION')
        if benchmark is not None:
            if qkey in benchmark_questions:
                flags.append('BENCHMARK_EXACT_QUESTION')
            elif any(SequenceMatcher(None, qkey, q).ratio() >= 0.88
                     for q in benchmark_doc_questions.get(row['doc_id'], [])):
                flags.append('BENCHMARK_SIMILAR_QUESTION')
        severe = {'IDENTIFIER_COLUMN', 'NON_MONETARY_VALUE', 'DUPLICATE_DRAFT_QUESTION',
                  'BENCHMARK_EXACT_QUESTION', 'BENCHMARK_SIMILAR_QUESTION'}
        if severe.intersection(flags):
            priority, action = 'P0', 'HOLD_AND_REWRITE'
        elif any(f in flags for f in ('GENERIC_PARAGRAPH_DRAFT', 'GENERIC_SECTION')):
            priority, action = 'P1', 'REWRITE_WITH_SOURCE_CONTEXT'
        else:
            priority, action = 'P2', 'CHECK_OFFICIAL_PDF_AND_AMENDMENTS'
        # Every candidate still requires source verification, independent of flags.
        flags.append('OFFICIAL_SOURCE_REVIEW_REQUIRED')
        for f in flags:
            flag_counts[f] += 1
        year_counts[row['as_of_year']] += 1
        priorities[priority] += 1
        report_rows.append({
            'priority': priority,
            'source_kind': kind,
            'academic_year': row['academic_year'],
            'candidate_id': row['id'],
            'candidate_sha256': candidate_fingerprint(row),
            'doc_id': row['doc_id'],
            'source_file': row['source_file'],
            'source_sha256': row['source_sha256'],
            'risk_flags': ';'.join(flags),
            'review_action': action,
            'question_draft': row['question'],
            'answer_draft': row['answer'],
            'section': row.get('table_section', ''),
            'row_label': row.get('table_row_label', ''),
            'column': row.get('table_column', ''),
            'evidence_quote': row['evidence_quote'],
            'human_decision': 'PENDING (EDIT ORIGINAL DECISION JSONL, NOT THIS CSV)',
            'reviewer': '',
            'review_notes': '',
        })
    report_rows.sort(key=lambda x: (x['priority'], x['academic_year'], x['doc_id'], x['candidate_id']))
    digest_map = {str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p): sha256(p)
                  for p in inputs if p.exists()}
    result = {
        'draft_candidates': len(all_rows),
        'paragraph_candidates': len(prose_rows),
        'table_candidates': len(table_rows),
        'years': {str(y): year_counts[y] for y in range(2022, 2027)},
        'priorities': {k: priorities[k] for k in ('P0', 'P1', 'P2')},
        'flags': dict(sorted(flag_counts.items())),
        'input_sha256': digest_map,
        'benchmark_provided': benchmark is not None,
        'benchmark_leakage_clearance': False,
        'human_approved': 0,
        'ready_for_training': False,
        'csv': str(output),
        'manifest': str(manifest),
        'notes': 'CSV is read-only review aid, not a signed review decision or a training dataset.',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    csv_created = False
    try:
        with output.open('x', newline='', encoding='utf-8-sig') as stream:
            csv_created = True
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for entry in report_rows:
                writer.writerow({key: _excel_safe(entry[key]) for key in FIELDS})
        with manifest.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write('\n')
    except Exception:
        if csv_created:
            output.unlink(missing_ok=True)
        raise
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Create DRAFT-ONLY unified human QA review worklist')
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--prose', type=Path, default=Path('src/lora/runs/candidates.jsonl'))
    parser.add_argument('--tables', type=Path, default=Path('src/lora/runs/table_candidates_v2.jsonl'))
    parser.add_argument('--registry', type=Path, default=Path('data/versioning/documents.jsonl'))
    parser.add_argument('--holds', type=Path, default=Path('data/versioning/publication_holds.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('src/lora/runs/review_packet_v2.csv'))
    parser.add_argument('--manifest', type=Path, default=Path('src/lora/runs/review_packet_v2_manifest.json'))
    parser.add_argument('--benchmark', type=Path, default=None,
                        help='Optional read-only frozen benchmark from data/eval owner')
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    def resolve(p: Path) -> Path:
        return p if p.is_absolute() else root / p
    report = generate_packet(root, resolve(args.prose), resolve(args.tables),
                             resolve(args.registry), resolve(args.holds),
                             resolve(args.output), resolve(args.manifest),
                             resolve(args.benchmark) if args.benchmark else None)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
