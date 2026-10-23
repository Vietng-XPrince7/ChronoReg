"""Offline tests: table QA is draft-only and bound to verified UET source."""
import hashlib

import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.review import review_template
from src.lora.table_candidates import propose_tables


SAMPLE = '''# HỌC BỔNG 2023-2024

# **1. Đối với chương trình đào tạo chuẩn**

| Khóa học | Loại Xuất sắc (đồng/tháng) | Loại Giỏi (đồng/tháng) |
|---|---:|---:|
|Khóa QH-2023|2.990.000đ|2.920.000đ|
|Khóa QH-2022|2.750.000đ|2.680.000đ|
'''


def context(tmp_path, text=SAMPLE, status=True, academic='2023-2024', topic='scholarship'):
    source = tmp_path / 'data/raw/uet/markdown/2023/scholarship.md'
    source.parent.mkdir(parents=True)
    source.write_text(text, encoding='utf-8')
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    registry = tmp_path / 'data/versioning/documents.jsonl'
    holds = tmp_path / 'data/versioning/publication_holds.jsonl'
    doc = dict(doc_id='uet-2023-scholarship', relative_path='2023/scholarship.md',
               content_sha256=sha, topic_hint=topic, academic_year_verified=academic,
               review_status='verified_against_source', policy_qa_ready=status)
    write_jsonl(registry, [doc]); write_jsonl(holds, [])
    dest = tmp_path / 'src/lora/runs/table_candidates.jsonl'
    return source, doc, registry, holds, dest


def test_2023_table_recovers_concrete_draft_QA(tmp_path):
    source, doc, registry, holds, dest = context(tmp_path)
    report = propose_tables(tmp_path, registry, holds, dest)
    assert report['candidates'] == 4
    assert report['years']['2023'] == 4 and report['auto_approved'] == 0
    rows = read_jsonl(dest)
    assert all(r['review_status'] == 'draft' and r['source_sha256'] == doc['content_sha256'] for r in rows)
    answer = next(r for r in rows if 'QH-2023' in r['question'] and 'Giỏi' in r['question'])
    assert answer['answer'] == '2.920.000đ'
    assert answer['evidence_quote'] in source.read_text(encoding='utf-8')
    assert '2023-2024' in answer['question']


def test_shared_review_template_accepts_table_drafts_without_approval(tmp_path):
    _, _, registry, holds, dest = context(tmp_path)
    propose_tables(tmp_path, registry, holds, dest)
    review = tmp_path/'table_reviews.jsonl'
    coverage = tmp_path/'table_coverage.csv'
    result = review_template(tmp_path, dest, registry, holds, review, coverage)
    assert result['candidates'] == 4 and result['approved'] == 0
    assert all(d['decision'] == 'pending' for d in read_jsonl(review))


def test_hold_blocks_table_generation(tmp_path):
    _, doc, registry, holds, dest = context(tmp_path)
    write_jsonl(holds, [dict(doc_id=doc['doc_id'], content_sha256=doc['content_sha256'],
                             reason='Original source needs verification')])
    report = propose_tables(tmp_path, registry, holds, dest)
    assert report['candidates'] == 0 and report['skipped']['blocked_or_unverified_docs'] == 1


def test_unreleased_and_wrong_topic_excluded(tmp_path):
    for attrs in ({'status':False}, {'topic':'research'}, {'academic':None}):
        case = tmp_path / str(len(list(tmp_path.iterdir())))
        _, _, registry, holds, dest = context(case, **attrs)
        assert propose_tables(case, registry, holds, dest)['candidates'] == 0


def test_mutated_source_fails_before_writing(tmp_path):
    source, _, registry, holds, dest = context(tmp_path)
    source.write_text(source.read_text(encoding='utf-8')+'\nchange', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA mismatch'):
        propose_tables(tmp_path, registry, holds, dest)
    assert not dest.exists()


def test_ambiguous_header_and_malformed_rows_not_proposed(tmp_path):
    text = '''# HỌC BỔNG\n\n| Khóa học | Loại Giỏi | Loại Giỏi |\n|---|---|---|\n|QH-2023|2.920.000|2.910.000|\n\n| Khóa học | Loại Giỏi |\n|---|---|\n|QH-2023|2.920.000|Wrong cell|\n'''
    _, _, registry, holds, dest = context(tmp_path, text=text)
    result = propose_tables(tmp_path, registry, holds, dest)
    assert result['candidates'] == 0
    assert result['skipped']['ambiguous_table_headers'] == 1


def test_non_overwrite_preserves_prior_manual_work(tmp_path):
    _, _, registry, holds, dest = context(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_text('DO NOT OVERWRITE', encoding='utf-8')
    with pytest.raises(FileExistsError, match='Refusing to overwrite'):
        propose_tables(tmp_path, registry, holds, dest)
    assert dest.read_text(encoding='utf-8') == 'DO NOT OVERWRITE'


def test_bounded_candidates_and_invalid_limit(tmp_path):
    _, _, registry, holds, dest = context(tmp_path)
    with pytest.raises(ValueError, match='max_per_doc'):
        propose_tables(tmp_path, registry, holds, dest, max_per_doc=0)
    result = propose_tables(tmp_path, registry, holds, dest, max_per_doc=2)
    assert result['candidates'] == 2


def test_no_heading_means_no_synthetic_context(tmp_path):
    text = '''| Khóa học | Loại Giỏi (đồng/tháng) |\n|---|---|\n|Khóa QH-2023|2.920.000đ|\n'''
    _, _, registry, holds, dest = context(tmp_path, text=text)
    assert propose_tables(tmp_path, registry, holds, dest)['candidates'] == 0
