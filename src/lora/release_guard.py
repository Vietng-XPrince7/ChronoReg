"""Training release interlock (fail-closed; no model imports).

This validates artifacts, not independent human identity or policy correctness.
An approved release dossier is a separate owner action, never generated here.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .contracts import read_jsonl, sha256, validate_training, validate_benchmark
from .intake_audit import ensure_curated

SCHEMA = 'chronoreg-lora-release/v1'
LEGACY_ID = re.compile(r'^train-20\d\d-\d{3}$')


def _within(repo: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: release references require repository-relative paths')
    file = (repo / relative).resolve()
    if not file.is_relative_to(repo.resolve()):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: referenced file escapes repository')
    return file


def require_training_release(repo: Path | None, prepared_dir: Path, year: int,
                             release_path: Path | None) -> dict:
    """Require explicit, checksum-bound owner release before non-dry-run training.

    Nothing here makes an AI review an independent human attestation.
    All source-review and leakage claims must be accepted upstream, not here.
    """
    if repo is None or release_path is None:
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: --release and repository root are required for live training')
    repo = repo.resolve()
    release_path = release_path.resolve()
    if not release_path.is_file() or not release_path.is_relative_to(repo):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: release dossier missing/outside repository')
    try:
        release = json.loads(release_path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: invalid release dossier') from exc
    if (release.get('schema') != SCHEMA or release.get('status') != 'owner_released'
            or release.get('independent_benchmark_review') is not True
            or release.get('leakage_dispositions_reviewed') is not True):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: owner release, benchmark review and leakage clearance required')
    owner = release.get('owner_attestation')
    if not isinstance(owner, dict) or not all(isinstance(owner.get(k), str) and owner[k].strip()
                                               for k in ('reviewer', 'reviewed_at', 'decision_note')):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: substantive owner attestation required')
    # Require the two ledgers to be present, accepted and pinned; no empty attestations.
    evidence = _within(repo, release.get('benchmark_evidence_ledger', ''))
    leakage = _within(repo, release.get('leakage_disposition_ledger', ''))
    if not evidence.is_file() or not leakage.is_file():
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: reviewed ledgers missing')
    if sha256(evidence) != release.get('benchmark_evidence_sha256') or sha256(leakage) != release.get('leakage_disposition_sha256'):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: reviewed ledger hashes changed')
    with evidence.open(encoding='utf-8-sig', newline='') as fh:
        evidence_rows = list(csv.DictReader(fh))
    if (len(evidence_rows) != 42 or len({r.get('benchmark_id') for r in evidence_rows}) != 42
            or any(r.get('owner_accepted', '').strip().upper() not in ('YES', 'TRUE')
                   or r.get('final_freeze_eligible', '').strip().upper() not in ('YES', 'TRUE')
                   for r in evidence_rows)):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: 42 benchmark corrections lack final acceptance')
    with leakage.open(encoding='utf-8-sig', newline='') as fh:
        leak_rows = list(csv.DictReader(fh))
    if (len(leak_rows) != 59 or len({(r.get('candidate_id'),r.get('benchmark_id')) for r in leak_rows}) != 59
            or any(r.get('training_payload_evidence_checked', '').strip().upper() != 'YES'
                   or r.get('fact_level_disposition', '').strip().upper() not in ('CLEARED','QUARANTINED')
                   or r.get('independent_reviewer_signoff', '').strip().upper() != 'YES'
                   for r in leak_rows)):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: 59 overlap dispositions not independently accepted')
    primary = _within(repo, release.get('benchmark_file', ''))
    train = _within(repo, release.get('curated_train_file', ''))
    decisions = _within(repo, release.get('qa_decisions_file', ''))
    for path in (primary, train, decisions):
        if not path.is_file():
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: required frozen input missing')
    if (sha256(primary) != release.get('benchmark_sha256')
            or sha256(train) != release.get('curated_train_sha256')
            or sha256(decisions) != release.get('qa_decisions_sha256')):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: released input hashes changed')
    rows = read_jsonl(train)
    bench = validate_benchmark(read_jsonl(primary))
    if len(bench) != 90 or len(rows) != 24:
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: expected 90 held-out and 24 curated QA')
    decisions_rows = read_jsonl(decisions)
    if len(decisions_rows) != 25 or len({x.get('candidate_id') for x in decisions_rows}) != 25 or any(x.get('decision') != 'approve' for x in decisions_rows):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: V3 decisions not 25 approved')
    quarantined = {'fact-review-2024-026'}
    candidate_ids = {x['candidate_id'] for x in decisions_rows} - quarantined
    approved_by_id = {d['candidate_id']: d for d in decisions_rows}
    if {x.get('id') for x in rows} != candidate_ids or any(LEGACY_ID.match(str(r.get('id',''))) for r in rows):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: curated IDs do not match V3 release')
    for row in rows:
        decision = approved_by_id[row['id']]
        if (row.get('question') != decision.get('question')
                or row.get('answer') != decision.get('answer')
                or row.get('doc_id') != decision.get('doc_id')
                or row.get('as_of_year') != decision.get('as_of_year')
                or row.get('candidate_sha256') != decision.get('candidate_sha256')):
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: curated QA differs from V3 content review decision')
    ensure_curated(rows)
    verified = validate_training(rows, repo, bench)
    manifest_path = prepared_dir / 'manifest.json'
    if not manifest_path.is_file() or sha256(manifest_path) != release.get('prepared_manifest_sha256'):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: prepared manifest is not owner-released')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if (manifest.get('train_sha256') != sha256(train)
            or manifest.get('benchmark_sha256') != sha256(primary)
            or manifest.get('total') != 24 or year not in manifest.get('years', [])):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: prepared manifest inputs mismatch')
    for yr in manifest['years']:
        file = prepared_dir / f'train_{yr}.jsonl'
        if not file.is_file() or manifest['year_sha256'].get(str(yr)) != sha256(file):
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: staged data hash mismatch')
        actual = read_jsonl(file)
        expected = [r for r in verified if r['as_of_year'] == yr]
        if actual != expected or len(actual) != manifest['counts'].get(str(yr)):
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: staged payload differs from verified curated input')
    return {'release_file_sha256': sha256(release_path), 'benchmark_sha256': sha256(primary),
            'curated_train_sha256': sha256(train), 'released_count': len(rows)}
