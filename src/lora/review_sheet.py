"""Human-editable CSV review sheets with fail-closed import into LoRA review JSONL.

No QA is approved by the tool. Reviewers must independently check official UET
sources and explicitly enter each decision. The imported JSONL is still subject
to review-finalize and the frozen benchmark gate before training.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from .contracts import read_jsonl, validate_benchmark, validate_training, write_jsonl, question_key
from .review import _approve_decisions, _read_candidates, candidate_fingerprint
from .review_packet import FIELDS as PACKET_FIELDS, _excel_safe

EDIT_FIELDS = ('decision', 'reviewed_question', 'verified_answer',
               'reviewer_name', 'review_date', 'review_note')
SHEET_FIELDS = PACKET_FIELDS + EDIT_FIELDS


def _load_packet(packet: Path, candidates: dict[str, dict]) -> list[dict[str, str]]:
    """Verify the read-only packet is still bound to source-verified candidates."""
    with packet.open('r', newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != PACKET_FIELDS:
            raise ValueError('Review packet columns differ from expected schema')
        rows = list(reader)
    if not rows or len(rows) != len(candidates):
        raise ValueError('Review packet and verified candidate counts do not match')
    seen = set()
    for row in rows:
        if None in row:
            raise ValueError('Review packet has additional columns')
        cid = row['candidate_id']
        if cid not in candidates or cid in seen:
            raise ValueError(f'Unknown/duplicate packet candidate: {cid}')
        seen.add(cid)
        cand = candidates[cid]
        expected = {
            'candidate_sha256': candidate_fingerprint(cand),
            'academic_year': cand['academic_year'],
            'doc_id': cand['doc_id'],
            'source_file': cand['source_file'],
            'source_sha256': cand['source_sha256'],
            'question_draft': _excel_safe(cand['question']),
            'answer_draft': _excel_safe(cand['answer']),
            'evidence_quote': _excel_safe(cand['evidence_quote']),
        }
        for field, value in expected.items():
            if row[field] != value:
                raise ValueError(f'{cid}: packet field {field} differs from verified candidate')
        if row['source_kind'] not in ('paragraph', 'table'):
            raise ValueError(f'{cid}: unknown source_kind')
    return rows


def _verified(repo: Path, prose: Path, tables: Path, registry: Path, holds: Path):
    prose_rows = _read_candidates(repo, prose, registry, holds)
    table_rows = _read_candidates(repo, tables, registry, holds)
    if not prose_rows and not table_rows:
        raise ValueError('No verified draft candidates')
    records = prose_rows + table_rows
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Candidate IDs duplicated across paragraph/table files')
    return {r['id']: r for r in records}, {
        **{r['id']: 'paragraph' for r in prose_rows},
        **{r['id']: 'table' for r in table_rows},
    }


def _guard_outputs(inputs: list[Path], outputs: list[Path]) -> None:
    resolved_inputs = {p.resolve() for p in inputs}
    resolved_outputs = [p.resolve() for p in outputs]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise ValueError('Output paths must differ')
    if resolved_inputs.intersection(resolved_outputs):
        raise ValueError('Output cannot replace input data')
    for p in outputs:
        if p.exists():
            raise FileExistsError(f'Existing file must not be overwritten: {p}')


def export_sheet(repo: Path, prose: Path, tables: Path, registry: Path,
                 holds: Path, packet: Path, sheet: Path) -> dict:
    _guard_outputs([prose, tables, registry, holds, packet], [sheet])
    candidates, kinds = _verified(repo, prose, tables, registry, holds)
    rows = _load_packet(packet, candidates)
    for row in rows:
        if row['source_kind'] != kinds[row['candidate_id']]:
            raise ValueError('Packet candidate source type changed')
    sheet.parent.mkdir(parents=True, exist_ok=True)
    with sheet.open('x', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=SHEET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, 'decision': 'pending', 'reviewed_question': '',
                             'verified_answer': '', 'reviewer_name': '',
                             'review_date': '', 'review_note': ''})
    return {'rows': len(rows), 'approved': 0, 'sheet': str(sheet),
            'editable_fields': list(EDIT_FIELDS), 'training_ready': False}


def import_sheet(repo: Path, prose: Path, tables: Path, registry: Path,
                 holds: Path, packet: Path, sheet: Path, combined: Path,
                 decisions: Path, benchmark: Path | None = None) -> dict:
    protected = [prose, tables, registry, holds, packet, sheet]
    if benchmark is not None:
        protected.append(benchmark)
    _guard_outputs(protected, [combined, decisions])
    candidates, kinds = _verified(repo, prose, tables, registry, holds)
    packets = _load_packet(packet, candidates)
    packet_map = {r['candidate_id']: r for r in packets}
    with sheet.open('r', newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != SHEET_FIELDS:
            raise ValueError('Edited sheet columns differ from expected schema')
        edited = list(reader)
    if len(edited) != len(packets):
        raise ValueError('Edited sheet must contain every original candidate exactly once')
    verdicts = []
    seen = set()
    for row in edited:
        if None in row:
            raise ValueError('Edited sheet has unexpected additional columns')
        cid = row.get('candidate_id')
        if cid not in candidates or cid in seen:
            raise ValueError(f'Unknown or duplicated edited candidate: {cid}')
        seen.add(cid)
        original = packet_map[cid]
        for field in PACKET_FIELDS:
            if row[field] != original[field]:
                raise ValueError(f'{cid}: immutable review column changed: {field}')
        if row['source_kind'] != kinds[cid]:
            raise ValueError(f'{cid}: candidate source type changed')
        status = row['decision'].strip().lower()
        if status not in ('pending', 'approve', 'reject'):
            raise ValueError(f'{cid}: decision must be pending, approve, or reject')
        question = row['reviewed_question'].strip()
        answer = row['verified_answer'].strip()
        reviewer = row['reviewer_name'].strip()
        date = row['review_date'].strip()
        note = row['review_note'].strip()
        if status == 'pending' and any((question, answer, reviewer, date, note)):
            raise ValueError(f'{cid}: pending decision contains edits; set approve/reject or clear fields')
        if status == 'approve':
            if not question or not answer:
                raise ValueError(f'{cid}: approval requires independently reviewed question and answer')
            if question_key(question) == question_key(candidates[cid]['question']):
                raise ValueError(f'{cid}: approval requires rewriting draft question')
            if question.lstrip().startswith(('=', '+', '-', '@')) or answer.lstrip().startswith(('=', '+', '-', '@')):
                raise ValueError(f'{cid}: review text begins with a spreadsheet formula prefix')
        if status == 'reject' and (question or answer):
            raise ValueError(f'{cid}: rejected row must leave reviewed question/answer empty')
        cand = candidates[cid]
        verdicts.append({
            'candidate_id': cid,
            'candidate_sha256': candidate_fingerprint(cand),
            'doc_id': cand['doc_id'], 'as_of_year': cand['as_of_year'],
            'source_file': cand['source_file'], 'evidence_quote': cand['evidence_quote'],
            'decision': status, 'reviewer': reviewer, 'reviewed_at': date,
            'review_note': note, 'question': question or cand['question'],
            'answer': answer or cand['answer'],
        })
    if set(candidates) != seen:
        raise ValueError('Missing decisions for some candidates')
    # Reuse authoritative SHA-bound approval checks; do not implement new shortcuts.
    validated_approved, stats = _approve_decisions(repo, list(candidates.values()), verdicts)
    bench_rows = None
    if benchmark is not None:
        bench_rows = validate_benchmark(read_jsonl(benchmark))
        if not bench_rows:
            raise ValueError('Explicit benchmark must not be empty')
    if validated_approved:
        validate_training(validated_approved, repo, bench_rows)
    # Only after all validations, produce new matching combined candidate and decision files.
    ordered = sorted(candidates.values(), key=lambda r: (r['as_of_year'], r['id']))
    verdicts.sort(key=lambda r: (r['as_of_year'], r['candidate_id']))
    combined.parent.mkdir(parents=True, exist_ok=True)
    decisions.parent.mkdir(parents=True, exist_ok=True)
    combined_written = False
    try:
        with combined.open('x', encoding='utf-8') as output:
            combined_written = True
            for rec in ordered:
                output.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + '\n')
        with decisions.open('x', encoding='utf-8') as output:
            for rec in verdicts:
                output.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + '\n')
    except Exception:
        if combined_written:
            combined.unlink(missing_ok=True)
        raise
    return {'candidates': len(candidates), 'decisions': stats,
            'approved': len(validated_approved), 'benchmark_provided': benchmark is not None,
            'benchmark_isolation_certified': False,
            'combined_candidates': str(combined), 'review_decisions': str(decisions),
            'approved_training_exported': False}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Export/import SHA-bound human-edited LoRA QA review sheets')
    parser.add_argument('action', choices=('export', 'import'))
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--prose', type=Path, default=Path('src/lora/runs/candidates.jsonl'))
    parser.add_argument('--tables', type=Path, default=Path('src/lora/runs/table_candidates_v2.jsonl'))
    parser.add_argument('--registry', type=Path, default=Path('data/versioning/documents.jsonl'))
    parser.add_argument('--holds', type=Path, default=Path('data/versioning/publication_holds.jsonl'))
    parser.add_argument('--packet', type=Path, default=Path('src/lora/runs/review_packet_v2.csv'))
    parser.add_argument('--sheet', type=Path, default=Path('src/lora/runs/review_sheet_v2.csv'))
    parser.add_argument('--combined', type=Path, default=Path('src/lora/runs/combined_candidates_v2.jsonl'))
    parser.add_argument('--decisions', type=Path, default=Path('src/lora/runs/combined_decisions_v2.jsonl'))
    parser.add_argument('--benchmark', type=Path, default=None)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    def resolve(p: Path) -> Path:
        return p if p.is_absolute() else repo / p
    common = [repo, resolve(args.prose), resolve(args.tables), resolve(args.registry),
              resolve(args.holds), resolve(args.packet), resolve(args.sheet)]
    if args.action == 'export':
        report = export_sheet(*common)
    else:
        report = import_sheet(*common, resolve(args.combined), resolve(args.decisions),
                              resolve(args.benchmark) if args.benchmark else None)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
