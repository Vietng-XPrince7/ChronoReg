"""Independent frozen benchmark evidence gate for QLoRA 3B."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from .contracts import sha256

def _within(repo: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: release references require repository-relative paths')
    file = (repo / relative).resolve()
    if not file.is_relative_to(repo.resolve()):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: referenced file escapes repository')
    return file


def _sha256_text(value: str) -> str:
    """Bind review entries to the exact UTF-8 answer, without normalization."""
    import hashlib
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _review_csv(repo: Path, release: dict, path_key: str, sha_key: str) -> list[dict]:
    path = _within(repo, release.get(path_key, ''))
    if not path.is_file() or sha256(path) != release.get(sha_key):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: review ledger absent or SHA changed')
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def require_full_benchmark_review(repo: Path, release: dict, benchmark: list[dict]) -> None:
    """Require row-by-row acceptance for every held-out ID and its exact answer.

    This checks completeness and binding, not the truthfulness/identity of a
    reviewer. It must not be used as an automatic approval mechanism.
    """
    ledger = _review_csv(repo, release, 'full_benchmark_review_ledger',
                         'full_benchmark_review_sha256')
    by_id = {r['id']: r for r in benchmark}
    if len(ledger) != len(benchmark) or len({r.get('benchmark_id') for r in ledger}) != len(benchmark):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: full benchmark ledger coverage mismatch')
    for item in ledger:
        case = by_id.get(item.get('benchmark_id'))
        if case is None:
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: unknown benchmark review ID')
        if (item.get('gold_answer_sha256') != _sha256_text(case['gold_answer'])
                or item.get('source_doc_id') != case['gold_doc_id']
                or item.get('source_sha256') != case.get('source_sha256')
                or str(item.get('as_of_year')) != str(case['as_of_year'])):
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: benchmark review does not match pinned gold/source/year')
        for field in ('gold_answer_verified', 'source_verified',
                      'effectivity_verified', 'independent_reviewer_signoff'):
            if item.get(field, '').strip().upper() != 'YES':
                raise RuntimeError('TRAINING_RELEASE_BLOCKED: incomplete independent benchmark review')
        if not item.get('reviewer_note', '').strip():
            raise RuntimeError('TRAINING_RELEASE_BLOCKED: benchmark review note missing')
    manifest_file = _within(repo, release.get('benchmark_freeze_manifest', ''))
    if not manifest_file.is_file() or sha256(manifest_file) != release.get('benchmark_freeze_manifest_sha256'):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: benchmark freeze artifact missing or changed')
    try:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError) as exc:
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: invalid benchmark freeze artifact') from exc
    if (manifest.get('schema') != 'chronoreg-benchmark-freeze/v1'
            or manifest.get('benchmark_frozen') is not True
            or manifest.get('owner_approved') is not True
            or manifest.get('benchmark_sha256') != release.get('benchmark_sha256')
            or manifest.get('full_benchmark_review_sha256') != release.get('full_benchmark_review_sha256')):
        raise RuntimeError('TRAINING_RELEASE_BLOCKED: benchmark freeze has not been accepted')
