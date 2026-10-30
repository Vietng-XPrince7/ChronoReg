"""Batch 4 integrity and publication-hold regression tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from src.versioning.core import (
    apply_publication_holds, validate_review_ledger, policy_qa_readiness,
    make_id, inventory, build, read_jsonl,
)


def _docs(tmp_path):
    corpus = tmp_path / 'data/raw/uet/markdown'
    corpus.mkdir(parents=True)
    path = corpus / '2022-hoc-phi.md'
    path.write_text('# Học phí năm học 2022-2023\n', encoding='utf8')
    rows = inventory(corpus)
    # Simulate an independently source-confirmed piece of metadata.
    rows[0]['review_status'] = 'verified_against_source'
    rows[0]['academic_year_verified'] = '2022-2023'
    rows[0]['eligible_for_policy_qa'] = True
    rows[0]['scope'] = 'Undergraduate tuition 2022-2023'
    return rows


def test_hold_prevents_verified_old_rate_from_going_to_policy_qa(tmp_path):
    docs = _docs(tmp_path)
    assert policy_qa_readiness(docs[0]) == 'reviewed_scope_and_time'
    apply_publication_holds(docs, [{
        'doc_id': docs[0]['doc_id'],
        'content_sha256': docs[0]['content_sha256'],
        'reason': 'Superseded by a later tuition adjustment',
        'evidence_reference': 'UET official adjustment page',
    }])
    assert policy_qa_readiness(docs[0]) == 'held_pending_source_or_content_review'


def test_publication_hold_refuses_stale_or_duplicate_records(tmp_path):
    docs = _docs(tmp_path)
    item = {'doc_id': docs[0]['doc_id'], 'content_sha256': '0'*64,
            'reason': 'Not safe without adjustment record', 'evidence_reference': 'UET'}
    with pytest.raises(ValueError, match='SHA mismatch'):
        apply_publication_holds(docs, [item])
    item['content_sha256'] = docs[0]['content_sha256']
    with pytest.raises(ValueError, match='duplicate'):
        apply_publication_holds(docs, [item, item])


def test_audit_ledger_enforces_identity_and_disposition(tmp_path):
    docs = _docs(tmp_path)
    item = {'doc_id': docs[0]['doc_id'], 'content_sha256': docs[0]['content_sha256'],
            'relative_path': docs[0]['relative_path'], 'disposition': 'quality_hold',
            'reason': 'Source layout corrupted', 'further_action': 'Compare PDF table'}
    validate_review_ledger(docs, [item])
    with pytest.raises(ValueError, match='Stale'):
        validate_review_ledger(docs, [{**item, 'content_sha256': 'a'*64}])
    with pytest.raises(ValueError, match='Unknown review disposition'):
        validate_review_ledger(docs, [{**item, 'disposition': 'auto_approve'}])


def test_empty_ledger_backward_compatible(tmp_path):
    docs = _docs(tmp_path)
    apply_publication_holds(docs, [])
    validate_review_ledger(docs, [])
    assert policy_qa_readiness(docs[0]) == 'reviewed_scope_and_time'
