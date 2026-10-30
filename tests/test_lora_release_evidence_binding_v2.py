"""Fail-closed evidence-binding checks for release guard v2; no model imports."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from src.lora.release_guard import require_full_benchmark_review, require_overlap_inventory_binding


def _csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path):
    cases = [dict(id='BENCH_ACT_001', gold_answer='một triệu', gold_doc_id='d1',
                  source_sha256='a' * 64, as_of_year=2026),
             dict(id='BENCH_SUP_001', gold_answer='hai triệu', gold_doc_id='d2',
                  source_sha256='b' * 64, as_of_year=2025)]
    rows = []
    for b in cases:
        rows.append(dict(benchmark_id=b['id'],
                         gold_answer_sha256=hashlib.sha256(b['gold_answer'].encode()).hexdigest(),
                         source_doc_id=b['gold_doc_id'], source_sha256=b['source_sha256'],
                         as_of_year=b['as_of_year'], gold_answer_verified='YES',
                         source_verified='YES', effectivity_verified='YES',
                         independent_reviewer_signoff='YES', reviewer_note='Reviewed original source'))
    path = tmp_path/'reviews.csv'
    digest = _csv(path, rows)
    m = tmp_path/'freeze.json'
    m.write_text(json.dumps(dict(schema='chronoreg-benchmark-freeze/v1',
                                 benchmark_frozen=True, owner_approved=True,
                                 benchmark_sha256='f'*64, full_benchmark_review_sha256=digest)),encoding='utf-8')
    manifest_hash = hashlib.sha256(m.read_bytes()).hexdigest()
    release=dict(full_benchmark_review_ledger='reviews.csv',full_benchmark_review_sha256=digest,
                 benchmark_freeze_manifest='freeze.json',benchmark_freeze_manifest_sha256=manifest_hash,
                 benchmark_sha256='f'*64)
    return cases, rows, path, m, release


def test_full_review_valid_binding(tmp_path):
    cases, _, _, _, release = _fixture(tmp_path)
    require_full_benchmark_review(tmp_path, release, cases)


def test_missing_full_review_blocks(tmp_path):
    cases, _, _, _, release = _fixture(tmp_path)
    release.pop('full_benchmark_review_ledger')
    with pytest.raises(RuntimeError,match='BLOCKED'):
        require_full_benchmark_review(tmp_path, release, cases)


def test_changed_gold_answer_blocks(tmp_path):
    cases, _, _, _, release = _fixture(tmp_path)
    cases[0]['gold_answer'] = 'khác'
    with pytest.raises(RuntimeError,match='pinned gold'):
        require_full_benchmark_review(tmp_path, release, cases)


def test_missing_case_review_blocks(tmp_path):
    cases, rows, path, _, release = _fixture(tmp_path)
    release['full_benchmark_review_sha256'] = _csv(path, rows[:-1])
    with pytest.raises(RuntimeError,match='coverage'):
        require_full_benchmark_review(tmp_path, release, cases)


def test_unapproved_review_blocks(tmp_path):
    cases, rows, path, _, release = _fixture(tmp_path)
    rows[0]['independent_reviewer_signoff']='NO'
    release['full_benchmark_review_sha256'] = _csv(path, rows)
    with pytest.raises(RuntimeError,match='incomplete independent'):
        require_full_benchmark_review(tmp_path, release, cases)


def test_freeze_false_blocks(tmp_path):
    cases, _, _, m, release = _fixture(tmp_path)
    freeze=json.loads(m.read_text(encoding='utf-8'))
    freeze['benchmark_frozen']=False
    m.write_text(json.dumps(freeze),encoding='utf-8')
    release['benchmark_freeze_manifest_sha256']=hashlib.sha256(m.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError,match='not been accepted'):
        require_full_benchmark_review(tmp_path, release, cases)


def test_overlap_inventory_exact_ids_and_quarantine(tmp_path):
    cases=[dict(id=f'B{i}') for i in range(59)]
    decisions=[{'candidate_id': f'C{i}'} for i in range(58)] + [{'candidate_id':'fact-review-2024-026'}]
    inv=[dict(candidate_id=d['candidate_id'],benchmark_id=c['id']) for d,c in zip(decisions,cases)]
    p=tmp_path/'pairs.csv'
    digest=_csv(p,inv)
    release={'overlap_inventory_file':'pairs.csv','overlap_inventory_sha256':digest}
    reviewed=[dict(r, fact_level_disposition='QUARANTINED' if r['candidate_id']=='fact-review-2024-026' else 'CLEARED') for r in inv]
    require_overlap_inventory_binding(tmp_path,release,reviewed,cases,decisions)
    reviewed[0]['benchmark_id'] = 'B50'
    with pytest.raises(RuntimeError,match='do not match pinned inventory'):
        require_overlap_inventory_binding(tmp_path,release,reviewed,cases,decisions)
    reviewed[0]['benchmark_id'] = 'B0'
    reviewed[-1]['fact_level_disposition']='CLEARED'
    with pytest.raises(RuntimeError,match='quarantine'):
        require_overlap_inventory_binding(tmp_path,release,reviewed,cases,decisions)
