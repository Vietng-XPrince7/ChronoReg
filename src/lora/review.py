"""Human QA review, provenance revalidation, and year coverage for LoRA.

A reviewer must explicitly accept and rewrite each generated question. Nothing in
this module generates an approval, approves a document, or trains a model.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from .contracts import (question_key, read_jsonl, sha256, validate_training,
                        write_jsonl)

SOURCE_ROOT = Path('data/raw/uet/markdown')
ACADEMIC_YEAR = re.compile(r'^(20\d{2})-(20\d{2})$')
HEX256 = re.compile(r'^[0-9a-f]{64}$')
DECISIONS = ('pending', 'approve', 'reject')


def candidate_fingerprint(candidate: dict[str, Any]) -> str:
    """Bind a review to the EXACT candidate fields, including original excerpt."""
    data = json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _documents(repo: Path, registry: Path, holds: Path) -> dict[str, dict]:
    if not registry.is_file():
        raise FileNotFoundError('Versioning registry missing. Run: py -m src.versioning.cli build')
    docs = read_jsonl(registry)
    if len({r.get('doc_id') for r in docs}) != len(docs):
        raise ValueError('Duplicate document IDs in registry')
    blocked = read_jsonl(holds) if holds.exists() else []
    hold_ids = set()
    for hold in blocked:
        if hold.get('doc_id') in hold_ids:
            raise ValueError('Duplicate publication hold IDs')
        hold_ids.add(hold.get('doc_id'))
        doc = next((r for r in docs if r.get('doc_id') == hold.get('doc_id')), None)
        if doc is None or doc.get('content_sha256') != hold.get('content_sha256'):
            raise ValueError('Stale or unknown publication hold')
    doc_index = {r['doc_id']: r for r in docs}
    for r in docs:
        if r.get('publication_hold_reason'):
            hold_ids.add(r['doc_id'])
        r['_qa_hold'] = r['doc_id'] in hold_ids
    return doc_index


def _source_path(repo: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel.startswith(SOURCE_ROOT.as_posix() + '/'):
        raise ValueError('QA source_file must be under data/raw/uet/markdown/')
    if Path(rel).is_absolute() or '\\' in rel:
        raise ValueError('QA source_file must be a POSIX repository-relative path')
    root = (repo / SOURCE_ROOT).resolve()
    file = (repo / rel).resolve()
    if not file.is_relative_to(root) or not file.is_file():
        raise ValueError(f'Missing/unsafe Markdown source: {rel}')
    return file


def _verify_candidate(candidate: dict, repo: Path, doc_index: dict) -> None:
    name = candidate.get('id')
    doc_id = candidate.get('doc_id')
    doc = doc_index.get(doc_id)
    if not doc:
        raise ValueError(f'{name}: unknown document {doc_id}')
    if (not doc.get('policy_qa_ready') or doc.get('review_status') != 'verified_against_source'
            or doc.get('_qa_hold')):
        raise ValueError(f'{name}: document not released for policy QA')
    year = candidate.get('as_of_year')
    if type(year) is not int or year not in range(2022, 2027):
        raise ValueError(f'{name}: invalid as_of_year')
    academic = f'{year}-{year+1}'
    if candidate.get('academic_year') != academic or doc.get('academic_year_verified') != academic:
        raise ValueError(f'{name}: wrong or unverified academic year')
    rel = (SOURCE_ROOT / doc['relative_path']).as_posix()
    if candidate.get('source_file') != rel:
        raise ValueError(f'{name}: wrong source_file for document')
    file = _source_path(repo, rel)
    digest = sha256(file)
    if (digest != doc.get('content_sha256') or digest != candidate.get('source_sha256')
            or not HEX256.fullmatch(digest)):
        raise ValueError(f'{name}: stale candidate or source SHA mismatch')
    excerpt = candidate.get('evidence_quote')
    if not isinstance(excerpt, str) or len(excerpt.strip()) < 30:
        raise ValueError(f'{name}: missing/short evidence quote')
    original = file.read_bytes().decode('utf-8-sig').replace('\r\n', '\n')
    if excerpt.replace('\r\n', '\n') not in original:
        raise ValueError(f'{name}: evidence quote is not in source')
    if candidate.get('review_status') != 'draft':
        raise ValueError(f'{name}: input candidates must remain drafts')
    for field in ('id', 'question', 'answer'):
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            raise ValueError(f'{name}: missing {field}')


def _read_candidates(repo: Path, candidates: Path, registry: Path, holds: Path) -> list[dict]:
    doc_index = _documents(repo, registry, holds)
    rows = read_jsonl(candidates)
    seen = set()
    for row in rows:
        _verify_candidate(row, repo, doc_index)
        if row['id'] in seen:
            raise ValueError(f'Duplicate QA candidate ID {row["id"]}')
        seen.add(row['id'])
    return rows


def review_template(repo: Path, candidates: Path, registry: Path, holds: Path,
                    output: Path, coverage: Path) -> dict:
    """Emit editable PENDING decisions with candidate hashes and gap statistics."""
    if output.exists():
        raise FileExistsError(f'Review decisions already exist; refusing to overwrite human work: {output}')
    rows = _read_candidates(repo, candidates, registry, holds)
    prepared = []
    for row in rows:
        prepared.append({
            'candidate_id': row['id'],
            'doc_id': row['doc_id'],
            'as_of_year': row['as_of_year'],
            'source_file': row['source_file'],
            'evidence_quote': row['evidence_quote'],
            'candidate_sha256': candidate_fingerprint(row),
            'decision': 'pending',
            'reviewer': '', 'reviewed_at': '',
            'review_note': '',
            'question': row['question'], 'answer': row['answer'],
        })
    write_jsonl(output, prepared)
    counts = Counter(row['as_of_year'] for row in rows)
    coverage_rows = []
    for year in range(2022, 2027):
        ids = {r['doc_id'] for r in rows if r['as_of_year'] == year}
        coverage_rows.append({'year': year, 'draft_candidates': counts[year],
                              'source_documents': len(ids), 'approved_qa': 0,
                              'status': 'requires_manual_review' if counts[year] else 'no_candidates'})
    _write_coverage(coverage, coverage_rows)
    return {'candidates': len(rows), 'years': {str(y): counts[y] for y in range(2022, 2027)},
            'template': str(output), 'coverage': str(coverage), 'approved': 0,
            'manual_approval_required': True}


def _write_coverage(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # No untrusted CSV formulas: only hardcoded labels and integer values.
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=('year', 'draft_candidates', 'source_documents',
                                                    'approved_qa', 'status'))
        writer.writeheader()
        writer.writerows(rows)


def _approve_decisions(repo: Path, candidates: list[dict], decisions: list[dict]) -> tuple[list[dict], dict]:
    index = {row['id']: row for row in candidates}
    seen = set()
    approved = []
    counters = Counter()
    for decision in decisions:
        cid = decision.get('candidate_id')
        if cid not in index or cid in seen:
            raise ValueError(f'Decision has unknown/duplicate candidate ID: {cid}')
        seen.add(cid)
        original = index[cid]
        for immutable in ('doc_id', 'as_of_year', 'source_file', 'evidence_quote'):
            if immutable in decision and decision[immutable] != original[immutable]:
                raise ValueError(f'{cid}: cannot change candidate provenance field {immutable}')
        if decision.get('candidate_sha256') != candidate_fingerprint(original):
            raise ValueError(f'{cid}: candidate changed since review template was made')
        verdict = decision.get('decision')
        if verdict not in DECISIONS:
            raise ValueError(f'{cid}: decision must be pending/approve/reject')
        counters[verdict] += 1
        if verdict == 'pending':
            continue
        reviewer = decision.get('reviewer')
        note = decision.get('review_note')
        when = decision.get('reviewed_at')
        if not isinstance(reviewer, str) or len(reviewer.strip()) < 2:
            raise ValueError(f'{cid}: reviewer is required')
        if not isinstance(note, str) or len(note.strip()) < 12:
            raise ValueError(f'{cid}: substantive review_note is required')
        if not isinstance(when, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', when):
            raise ValueError(f'{cid}: reviewed_at must be YYYY-MM-DD')
        try:
            date.fromisoformat(when)
        except ValueError as exc:
            raise ValueError(f'{cid}: invalid reviewed_at date') from exc
        if verdict == 'reject':
            continue
        question, answer = decision.get('question'), decision.get('answer')
        if not isinstance(question, str) or not question.strip() or len(question) > 1500:
            raise ValueError(f'{cid}: invalid approved question')
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 5000:
            raise ValueError(f'{cid}: invalid approved answer')
        if question_key(question) == question_key(original['question']):
            raise ValueError(f'{cid}: rewrite the generic draft question before approving')
        if question_key(question) in {'', 'none', 'n/a'} or '<' in question or '>' in question:
            raise ValueError(f'{cid}: placeholder/markup in approved question')
        row = {k: original[k] for k in ('id', 'doc_id', 'as_of_year', 'academic_year',
                                        'evidence_quote', 'source_file', 'source_sha256')}
        row.update({'question': question.strip(), 'answer': answer.strip(), 'review_status': 'approved',
                    'reviewer': reviewer.strip(), 'reviewed_at': when,
                    'review_note': note.strip(), 'candidate_sha256': candidate_fingerprint(original)})
        approved.append(row)
    if set(index) - seen:
        raise ValueError(f'Missing decisions for {len(set(index) - seen)} candidates')
    return approved, dict(counters)


def finalize_review(repo: Path, candidates: Path, decisions_path: Path, registry: Path, holds: Path,
                    output: Path, coverage: Path, benchmark: Path | None = None) -> dict:
    """Produce a SHA/source-bound approved subset; benchmark withheld for final prepare.

    Output is *not* written until every decision/source/baseline validation succeeds.
    An empty approved set is permitted and explicitly reported for initial reviews.
    """
    if output.exists():
        raise FileExistsError(f'Approved QA already exists; refusing to overwrite reviewed data: {output}')
    candidates_rows = _read_candidates(repo, candidates, registry, holds)
    decisions = read_jsonl(decisions_path)
    approved, tally = _approve_decisions(repo, candidates_rows, decisions)
    if approved:
        # This does not prove semantic validity; human verification is mandatory.
        validated = validate_training(approved, repo)
        if len(validated) != len(approved):
            raise ValueError('Training contract unexpectedly dropped approved QAs')
    benchmark_checked = False
    if benchmark is not None:
        from .contracts import validate_benchmark
        benchmark_rows = validate_benchmark(read_jsonl(benchmark))
        if not benchmark_rows:
            raise ValueError('An explicitly provided benchmark must not be empty')
        if approved:
            validate_training(approved, repo, benchmark_rows)
        benchmark_checked = True
    counts = Counter(row['as_of_year'] for row in approved)
    source_docs = {year: {r['doc_id'] for r in candidates_rows if r['as_of_year'] == year}
                   for year in range(2022, 2027)}
    candidate_counts = Counter(r['as_of_year'] for r in candidates_rows)
    coverage_rows = [{'year': y, 'draft_candidates': candidate_counts[y],
                      'source_documents': len(source_docs[y]), 'approved_qa': counts[y],
                      'status': ('reviewed_with_qa' if counts[y] else 'no_approved_qa')}
                     for y in range(2022, 2027)]
    # Commit both results only after the review file and all document provenance validate.
    write_jsonl(output, approved)
    _write_coverage(coverage, coverage_rows)
    return {'approved': len(approved), 'decisions': tally, 'benchmark_overlap_checked': benchmark_checked,
            'benchmark_still_required_for_prepare': not benchmark_checked,
            'years': {str(y): counts[y] for y in range(2022, 2027)},
            'output': str(output), 'coverage': str(coverage),
            'semantic_accuracy_requires_human_review': True}
