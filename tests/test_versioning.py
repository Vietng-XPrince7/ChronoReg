"""Temporal integrity tests: unverified metadata must never be treated as legal truth."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.versioning.core import (
    apply_reviews, build, export_chunks, inventory, make_id, query, read_jsonl,
    validate_relations,
)


def make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / 'data/raw/uet/markdown'
    (root / '2026').mkdir(parents=True)
    (root / '2025').mkdir(parents=True)
    (root / '2025/Quy_dinh_muc_thu_hoc_phi_2025.md').write_text(
        '# Học phí năm học 2025-2026\nNguồn: https://uet.edu.vn/source\n', encoding='utf-8')
    (root / '2026/Quy_dinh_muc_thu_hoc_phi_2026.md').write_text(
        '# Học phí năm học 2026-2027\nĐiều chỉnh mức thu\n', encoding='utf-8')
    (root / '2026/Hoc_bong_2026.md').write_text(
        '# Danh sách sinh viên đạt học bổng\nTên học viên: Test\n', encoding='utf-8')
    return root


def approved_review(d):
    return {'doc_id': d['doc_id'], 'content_sha256': d['content_sha256'],
            'review_status': 'verified_against_source', 'evidence_reference': 'page 1 original PDF',
            'academic_year': '2025-2026', 'issued_date': '2025-09-29',
            'effective_from': '2025-09-29', 'effective_until_exclusive': '2026-09-01',
            'scope': 'undergraduate cohort QH-2025'}


def test_inventory_is_stable_and_does_not_infer_legal_effect(tmp_path):
    docs = inventory(make_corpus(tmp_path))
    assert len(docs) == 3
    assert docs == inventory(tmp_path / 'data/raw/uet/markdown')
    d = next(d for d in docs if d['folder_year_hint'] == '2025')
    assert d['academic_year_candidates'] == ['2025-2026']
    assert d['effective_from'] is None and d['issued_date'] is None
    assert d['source_url_in_text'] == 'https://uet.edu.vn/source'
    assert d['source_path'].startswith('data/raw/uet/markdown/')
    assert len({d['doc_id'] for d in docs}) == 3
    listing = next(d for d in docs if d['relative_path'].endswith('Hoc_bong_2026.md'))
    assert listing['eligible_for_policy_qa'] is False


def test_asof_unreviewed_never_marked_in_effect(tmp_path):
    docs = inventory(make_corpus(tmp_path))
    results = query(docs, topic='tuition', as_of='2026-01-02')
    assert results and {r['temporal_match'] for r in results} == {'unknown_unverified'}


def test_review_requires_sha_and_evidence_and_precise_dates(tmp_path):
    docs = inventory(make_corpus(tmp_path))
    target = next(d for d in docs if d['folder_year_hint'] == '2025')
    review = approved_review(target)
    with pytest.raises(ValueError, match='SHA mismatch'):
        apply_reviews(docs, [{**review, 'content_sha256': 'bad'}])
    with pytest.raises(ValueError, match='evidence_reference'):
        apply_reviews(docs, [{**review, 'evidence_reference': ''}])
    with pytest.raises(ValueError, match='Invalid effective interval'):
        apply_reviews(docs, [{**review, 'effective_until_exclusive': '2024-01-01'}])
    apply_reviews(docs, [review])
    inside = query(docs, topic='tuition', as_of='2026-01-02')
    checked = next(d for d in inside if d['doc_id'] == target['doc_id'])
    assert checked['temporal_match'] == 'inside_verified_interval'
    assert next(d for d in inside if d['doc_id'] != target['doc_id'])['temporal_match'] == 'unknown_unverified'
    outside = query(docs, topic='tuition', as_of='2026-09-01')
    assert next(d for d in outside if d['doc_id'] == target['doc_id'])['temporal_match'] == 'outside_verified_interval'


def test_unknown_expiration_is_not_assumed_open_ended(tmp_path):
    docs = inventory(make_corpus(tmp_path))
    target = docs[0]
    rev = approved_review(target)
    rev.pop('effective_until_exclusive')
    apply_reviews(docs, [rev])
    selected = next(d for d in query(docs, as_of='2026-01-02') if d['doc_id'] == target['doc_id'])
    assert selected['temporal_match'] == 'unknown_end_date'


def test_relation_requires_review_sha_scope_and_no_cycles(tmp_path):
    docs = inventory(make_corpus(tmp_path))
    left, right = docs[0], docs[1]
    row = {'from_doc_id': left['doc_id'], 'to_doc_id': right['doc_id'],
           'from_sha256': left['content_sha256'], 'to_sha256': right['content_sha256'],
           'review_status': 'verified_against_source', 'evidence_quote': 'Nguồn: https://uet.edu.vn/source',
           'relation_type': 'amends', 'applicability_scope': 'cohort 2025'}
    assert len(validate_relations(docs, [row], tmp_path / 'data/raw/uet/markdown')) == 1
    with pytest.raises(ValueError, match='applicability_scope'):
        validate_relations(docs, [{**row, 'applicability_scope': ''}])
    with pytest.raises(ValueError, match='Stale relation'):
        validate_relations(docs, [{**row, 'from_sha256': 'invalid'}])
    reverse = {**row, 'from_doc_id': right['doc_id'], 'to_doc_id': left['doc_id'],
               'from_sha256': right['content_sha256'], 'to_sha256': left['content_sha256']}
    with pytest.raises(ValueError, match='cycle'):
        validate_relations(docs, [row, reverse])


def test_build_preserves_review_files_and_exports_reversible_chunks(tmp_path):
    make_corpus(tmp_path)
    out = tmp_path / 'data/versioning'
    out.mkdir(parents=True)
    (out / 'reviewed_documents.jsonl').write_text('', encoding='utf-8')
    (out / 'approved_relations.jsonl').write_text('', encoding='utf-8')
    result = build(tmp_path)
    assert result['total'] == 3 and result['approved_relations'] == 0
    docs = read_jsonl(out / 'documents.jsonl')
    assert docs
    assert (out / 'coverage_by_folder.csv').exists()
    count = export_chunks(docs, tmp_path, out / 'rag_chunks.jsonl', max_chars=300)
    assert count == 0  # Unreviewed documents must not reach the reviewed output.
    assert all(not d['policy_qa_ready'] for d in docs)
    count = export_chunks(docs, tmp_path, out / 'rag_chunks_draft.jsonl',
                          max_chars=300, include_unreviewed=True)
    assert count == 2  # Candidate export excludes scholarship recipient lists.
    for c in read_jsonl(out / 'rag_chunks_draft.jsonl'):
        original = (tmp_path / 'data/raw/uet/markdown' / next(
            d['relative_path'] for d in docs if d['doc_id'] == c['doc_id'])).read_text(encoding='utf-8')
        assert original[c['start_char']:c['end_char']] == c['text']
    # A changed source invalidates an earlier manual approval; nothing is silently promoted.
    entry = docs[0]
    with (out / 'reviewed_documents.jsonl').open('w', encoding='utf-8') as f:
        f.write(json.dumps(approved_review(entry)) + '\n')
    built = build(tmp_path)
    assert built['policy_qa_ready'] == 1
    updated_docs = read_jsonl(out / 'documents.jsonl')
    assert export_chunks(updated_docs, tmp_path, out / 'rag_chunks.jsonl', max_chars=300) == 1
    assert all(chunk['policy_qa_ready'] for chunk in read_jsonl(out / 'rag_chunks.jsonl'))
    (tmp_path / 'data/raw/uet/markdown' / entry['relative_path']).write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='Stale document review'):
        build(tmp_path)


def test_qa_gate_requires_verified_scope_and_time(tmp_path):
    make_corpus(tmp_path)
    build(tmp_path)
    out = tmp_path / 'data/versioning'
    docs = read_jsonl(out / 'documents.jsonl')
    target = next(d for d in docs if d['folder_year_hint'] == '2025')
    assert target['eligible_for_policy_qa'] is True
    assert target['policy_qa_readiness'] == 'unreviewed'
    review = approved_review(target)
    review.pop('scope')
    (out / 'reviewed_documents.jsonl').write_text(json.dumps(review) + '\n', encoding='utf-8')
    build(tmp_path)
    updated = read_jsonl(out / 'documents.jsonl')
    r = next(d for d in updated if d['doc_id'] == target['doc_id'])
    assert r['policy_qa_readiness'] == 'missing_verified_scope'
    assert export_chunks(updated, tmp_path, out / 'rag_chunks.jsonl') == 0


def test_provisional_fee_notice_excluded(tmp_path):
    corpus = make_corpus(tmp_path)
    (corpus / '2025/Ke_hoach_thu_hoc_phi_2025.md').write_text(
        '# Tạm thu học phí năm học 2025-2026\n', encoding='utf-8')
    entry = next(d for d in inventory(corpus) if 'Ke_hoach_thu' in d['relative_path'])
    assert entry['document_kind_hint'] == 'provisional_notice'
    assert entry['eligible_for_policy_qa'] is False


def test_title_skips_letterhead_and_generic_decision(tmp_path):
    corpus = make_corpus(tmp_path)
    original = corpus / '2025/Quy_dinh_muc_thu_hoc_phi_2025.md'
    original.write_text(
        'ĐẠI HỌC QUỐC GIA HÀ NỘI **TRƯỜNG ĐẠI HỌC CÔNG NGHỆ**\n'
        '# QUYẾT ĐỊNH\n'
        '**QUY ĐỊNH ĐỊNH MỨC THU HỌC PHÍ NĂM HỌC 2025-2026**\n',
        encoding='utf-8')
    doc = next(d for d in inventory(corpus) if d['folder_year_hint'] == '2025')
    assert doc['title_hint'] == 'QUY ĐỊNH ĐỊNH MỨC THU HỌC PHÍ NĂM HỌC 2025-2026'
