"""Strict research data-release gate for the separate 3B QLoRA experiment.

The existing 0.5B V1 release gate remains unchanged. No approval files are
created by this module. Ledger completeness is not proof of reviewer identity.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .contracts import (read_jsonl, sha256, validate_benchmark,
                        validate_training, question_key)
from .release_guard import require_full_benchmark_review

SCHEMA = 'chronoreg-qlora3b-release/v1'
YEARS = [2022, 2023, 2024, 2025, 2026]


def within(repo: Path, path: str) -> Path:
    if not isinstance(path, str) or not path.strip() or Path(path).is_absolute():
        raise RuntimeError('RELEASE_BLOCKED: file must be a repository-relative path')
    resolved = (repo / path).resolve()
    if not resolved.is_relative_to(repo.resolve()) or not resolved.is_file():
        raise RuntimeError('RELEASE_BLOCKED: source missing or outside repository')
    return resolved


def pin(repo: Path, release: dict, path_key: str, sha_key: str) -> Path:
    file = within(repo, release.get(path_key, ''))
    if sha256(file) != release.get(sha_key):
        raise RuntimeError(f'RELEASE_BLOCKED: changed source/ledger {path_key}')
    return file


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def digest(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def _all_yes(row: dict, fields: tuple[str, ...]) -> bool:
    return all(str(row.get(k, '')).strip().upper() == 'YES' for k in fields)


def authorize(repo: Path, cfg: dict, prepared_dir: Path, release_path: Path | None) -> dict:
    """Verify manually issued, SHA-locked evidence for >24 approved training QA.

    Rejects older 200 legacy pseudo-QA and draft curricula. Reuses the full
    benchmark-row review gate from the existing ChronoReg release code.
    """
    repo = repo.resolve()
    if release_path is None or not release_path.is_file() or not release_path.resolve().is_relative_to(repo):
        raise RuntimeError('RELEASE_BLOCKED: a real owner release dossier inside repo is required')
    release = json.loads(release_path.read_text(encoding='utf-8-sig'))
    if (release.get('schema') != SCHEMA or release.get('status') != 'owner_released'
            or release.get('independent_training_review') is not True
            or release.get('independent_benchmark_review') is not True
            or release.get('semantic_leakage_reviewed') is not True):
        raise RuntimeError('RELEASE_BLOCKED: independent QA, benchmark and leakage reviews required')
    attestation = release.get('owner_attestation') or {}
    if any(not isinstance(attestation.get(k), str) or not attestation[k].strip()
           for k in ('reviewer', 'reviewed_at', 'decision_note')):
        raise RuntimeError('RELEASE_BLOCKED: owner attestation missing')
    train_file = pin(repo, release, 'curated_train_file', 'curated_train_sha256')
    benchmark_file = pin(repo, release, 'benchmark_file', 'benchmark_sha256')
    configured_benchmark = within(repo, cfg.get('benchmark', ''))
    if configured_benchmark != benchmark_file:
        raise RuntimeError('RELEASE_BLOCKED: config benchmark differs from frozen release')
    qa_ledger_file = pin(repo, release, 'qa_review_ledger', 'qa_review_sha256')
    # Independently accepted V3 correction and overlap ledgers, inherited evidence
    # plus NEW full per-row QA review for the 3B train set.
    corrections = csv_rows(pin(repo, release, 'benchmark_evidence_ledger',
                               'benchmark_evidence_sha256'))
    overlaps = csv_rows(pin(repo, release, 'leakage_disposition_ledger',
                            'leakage_disposition_sha256'))
    inventory = csv_rows(pin(repo, release, 'overlap_inventory_file',
                             'overlap_inventory_sha256'))
    if (len(corrections) != 42 or len({x.get('benchmark_id') for x in corrections}) != 42
            or any(not _all_yes(x, ('owner_accepted', 'final_freeze_eligible')) for x in corrections)):
        raise RuntimeError('RELEASE_BLOCKED: 42 correction decisions are not accepted')
    overlap_keys = {(x.get('candidate_id'), x.get('benchmark_id')) for x in overlaps}
    if (len(overlaps) != 59 or len(overlap_keys) != 59
            or len(inventory) != 59 or len({(x.get('candidate_id'), x.get('benchmark_id')) for x in inventory}) != 59
            or overlap_keys != {(x.get('candidate_id'), x.get('benchmark_id')) for x in inventory}
            or any(not _all_yes(x, ('training_payload_evidence_checked', 'independent_reviewer_signoff'))
                   or x.get('fact_level_disposition', '').strip().upper() not in ('CLEARED', 'QUARANTINED')
                   for x in overlaps)):
        raise RuntimeError('RELEASE_BLOCKED: 59 overlap dispositions are not accepted')
    if any(x.get('candidate_id') == 'fact-review-2024-026'
           and x.get('fact_level_disposition', '').strip().upper() != 'QUARANTINED'
           for x in overlaps):
        raise RuntimeError('RELEASE_BLOCKED: quarantine decision must be retained')

    benchmark = validate_benchmark(read_jsonl(benchmark_file))
    if len(benchmark) != 90:
        raise RuntimeError('RELEASE_BLOCKED: 90 frozen benchmark cases required')
    # Includes 90 individual review rows, source/year/hash, independent signoff,
    # frozen benchmark manifest and SHA binding.
    require_full_benchmark_review(repo, release, benchmark)

    raw = read_jsonl(train_file)
    if any(str(x.get('id', '')).startswith('train-20') for x in raw):
        raise RuntimeError('RELEASE_BLOCKED: legacy template QA cannot be reapproved unchanged')
    training = validate_training(raw, repo, benchmark)
    counts = {str(y): sum(x['as_of_year'] == y for x in training) for y in YEARS}
    if (len(training) < cfg['minimum_total_qa']
            or any(c < cfg['minimum_qa_per_year'] for c in counts.values())):
        raise RuntimeError('RELEASE_BLOCKED: insufficient curated training examples per year')
    if set(counts) != {str(y) for y in YEARS}:
        raise RuntimeError('RELEASE_BLOCKED: wrong training years')
    records = csv_rows(qa_ledger_file)
    by_id = {x.get('candidate_id'): x for x in records}
    if len(records) != len(training) or len(by_id) != len(training):
        raise RuntimeError('RELEASE_BLOCKED: each QA requires independent review ledger row')
    for q in raw:
        review = by_id.get(q['id'])
        if (review is None or review.get('decision') != 'approve'
                or not _all_yes(review, ('source_verified', 'cohort_effectivity_verified',
                                         'semantic_leakage_cleared', 'independent_reviewer_signoff'))
                or not review.get('reviewer_note', '').strip()
                or not review.get('reviewer', '').strip()
                or not review.get('reviewed_at', '').strip()
                or review.get('question_sha256') != digest(q['question'])
                or review.get('answer_sha256') != digest(q['answer'])
                or review.get('source_sha256') != q['source_sha256']):
            raise RuntimeError(f'RELEASE_BLOCKED: missing/mismatched QA review: {q["id"]}')
    # Frozen staging manifest must match source train + heldout benchmark.
    manifest_file = prepared_dir / 'manifest.json'
    if not manifest_file.is_file() or sha256(manifest_file) != release.get('prepared_manifest_sha256'):
        raise RuntimeError('RELEASE_BLOCKED: staging manifest not owner pinned')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if (manifest.get('train_sha256') != sha256(train_file)
            or manifest.get('benchmark_sha256') != sha256(benchmark_file)
            or manifest.get('years') != YEARS or manifest.get('total') != len(training)
            or manifest.get('counts') != counts):
        raise RuntimeError('RELEASE_BLOCKED: staging does not match frozen sources')
    for y in YEARS:
        stage = prepared_dir / f'train_{y}.jsonl'
        expected = [q for q in training if q['as_of_year'] == y]
        if (not stage.is_file() or sha256(stage) != manifest['year_sha256'].get(str(y))
                or read_jsonl(stage) != expected):
            raise RuntimeError('RELEASE_BLOCKED: staged training data changed')
    return {'release_sha256': sha256(release_path),
            'benchmark_sha256': sha256(benchmark_file),
            'training_sha256': sha256(train_file),
            'training_rows': len(training), 'counts': counts}
