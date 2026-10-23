"""Offline, source-bound human QA review tests; never download or use a model."""
import hashlib
from pathlib import Path

import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.review import candidate_fingerprint, finalize_review, review_template


def fixture(tmp_path: Path):
    path = tmp_path / 'data/raw/uet/markdown/2025/tuition.md'
    path.parent.mkdir(parents=True)
    evidence = ('Trong năm học 2025-2026, chương trình minh họa áp dụng mức học phí '
                'được nêu riêng trong văn bản thử nghiệm phục vụ unit test.')
    path.write_text('# Học phí\n\n' + evidence + '\n', encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = dict(doc_id='uet-example', relative_path='2025/tuition.md',
               content_sha256=digest, academic_year_verified='2025-2026',
               review_status='verified_against_source', policy_qa_ready=True)
    candidate = dict(id='lora-2025-a', doc_id='uet-example', as_of_year=2025,
                     academic_year='2025-2026', source_sha256=digest,
                     source_file='data/raw/uet/markdown/2025/tuition.md',
                     evidence_quote=evidence, question='Theo văn bản, mục này quy định gì?',
                     answer=evidence, review_status='draft')
    registry = tmp_path / 'data/versioning/documents.jsonl'
    holds = tmp_path / 'data/versioning/publication_holds.jsonl'
    candidates = tmp_path / 'draft.jsonl'
    decisions = tmp_path / 'reviews.jsonl'
    output = tmp_path / 'approved.jsonl'
    coverage = tmp_path / 'coverage.csv'
    write_jsonl(registry, [doc]); write_jsonl(holds, []); write_jsonl(candidates, [candidate])
    paths = (candidates, registry, holds, decisions, output, coverage)
    return path, doc, candidate, paths


def start(tmp_path):
    path, doc, row, (candidates, registry, holds, decisions, output, coverage) = fixture(tmp_path)
    report = review_template(tmp_path, candidates, registry, holds, decisions, coverage)
    assert report['approved'] == 0 and report['years']['2025'] == 1
    assert report['years']['2022'] == 0
    return path, doc, row, (candidates, registry, holds, decisions, output, coverage)


def sign(row, question='Năm 2025-2026 văn bản thử nghiệm nói gì về mức học phí?'):
    return dict(row, decision='approve', reviewer='QA Reviewer',
                reviewed_at='2026-10-23',
                review_note='Confirmed scope and exact passage against the fixture source.',
                question=question, answer='Áp dụng mức học phí trong văn bản thử nghiệm.')


def test_review_template_never_self_approves(tmp_path):
    *_, files = start(tmp_path)
    decisions = read_jsonl(files[3]); assert len(decisions) == 1
    assert decisions[0]['decision'] == 'pending'
    assert decisions[0]['reviewer'] == ''
    assert len(decisions[0]['candidate_sha256']) == 64
    assert '2023,0,0,0,no_candidates' in files[5].read_text(encoding='utf-8')


def test_empty_approvals_are_explicit(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    result = finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    assert result['approved'] == 0 and result['benchmark_still_required_for_prepare']
    assert read_jsonl(output) == []


def test_approved_requires_a_person_and_question_rewrite(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    rows = read_jsonl(decisions)
    rows[0]['decision'] = 'approve'
    write_jsonl(decisions, rows)
    with pytest.raises(ValueError, match='reviewer'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    write_jsonl(decisions, [sign(rows[0], question=rows[0]['question'])])
    with pytest.raises(ValueError, match='rewrite'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    assert not output.exists()


def test_approved_and_provenance_and_benchmark_flag(tmp_path):
    _, _, original, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    write_jsonl(decisions, [sign(read_jsonl(decisions)[0])])
    report = finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    assert report['approved'] == 1 and not report['benchmark_overlap_checked']
    qa = read_jsonl(output)[0]
    assert qa['review_status'] == 'approved' and qa['doc_id'] == original['doc_id']
    assert qa['reviewer'] == 'QA Reviewer'
    assert qa['candidate_sha256'] == candidate_fingerprint(original)
    assert '2025,1,1,1,reviewed_with_qa' in coverage.read_text(encoding='utf-8')


def test_rejected_is_not_training_data(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    row = read_jsonl(decisions)[0]
    row.update(decision='reject', reviewer='QA Reviewer', reviewed_at='2026-10-23',
               review_note='This passage is ambiguous and cannot be used for QA.')
    write_jsonl(decisions, [row])
    result = finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    assert result['decisions']['reject'] == 1 and read_jsonl(output) == []


def test_candidate_mutation_detected(tmp_path):
    _, _, row, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    changed = dict(row, answer='ALTERED ANSWER')
    write_jsonl(candidates, [changed]); write_jsonl(decisions, [sign(read_jsonl(decisions)[0])])
    with pytest.raises(ValueError, match='candidate changed'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)


def test_changed_source_refused(tmp_path):
    src, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    src.write_text(src.read_text(encoding='utf-8') + 'Changed.', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA mismatch'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)


def test_publication_hold_refused_even_if_registry_says_ready(tmp_path):
    _, doc, _, (candidates, registry, holds, decisions, output, coverage) = fixture(tmp_path)
    write_jsonl(holds, [dict(doc_id=doc['doc_id'], content_sha256=doc['content_sha256'],
                             reason='content under review')])
    with pytest.raises(ValueError, match='not released'):
        review_template(tmp_path, candidates, registry, holds, decisions, coverage)


def test_missing_reviewed_academic_year_refused(tmp_path):
    _, doc, _, (candidates, registry, holds, decisions, output, coverage) = fixture(tmp_path)
    write_jsonl(registry, [dict(doc, academic_year_verified=None)])
    with pytest.raises(ValueError, match='academic year'):
        review_template(tmp_path, candidates, registry, holds, decisions, coverage)


def test_unreleased_document_refused(tmp_path):
    _, doc, _, (candidates, registry, holds, decisions, output, coverage) = fixture(tmp_path)
    write_jsonl(registry, [dict(doc, policy_qa_ready=False)])
    with pytest.raises(ValueError, match='not released'):
        review_template(tmp_path, candidates, registry, holds, decisions, coverage)


def test_wrong_document_path_refused(tmp_path):
    _, _, row, (candidates, registry, holds, decisions, output, coverage) = fixture(tmp_path)
    write_jsonl(candidates, [dict(row, source_file='../../outside.md')])
    with pytest.raises(ValueError, match='wrong source_file'):
        review_template(tmp_path, candidates, registry, holds, decisions, coverage)


def test_benchmark_overlap_blocks_release(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    row = sign(read_jsonl(decisions)[0]); write_jsonl(decisions, [row])
    benchmark_path = tmp_path / 'benchmark.jsonl'
    write_jsonl(benchmark_path, [{'id':'bench-1', 'question':row['question'],
                                  'gold_answer':'Reference', 'gold_doc_id':'uet-example',
                                  'as_of_year':2025, 'type':'historical'}])
    with pytest.raises(ValueError, match='overlaps'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage, benchmark_path)
    assert not output.exists()


def test_benchmark_separation_success(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    write_jsonl(decisions, [sign(read_jsonl(decisions)[0])])
    bench = tmp_path/'benchmark.jsonl'
    write_jsonl(bench, [{'id':'other-id','question':'Separate test question?',
                         'gold_answer':'Answer','gold_doc_id':'uet-example',
                         'as_of_year':2025,'type':'current'}])
    result = finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage, bench)
    assert result['benchmark_overlap_checked'] and result['approved'] == 1


def test_missing_candidate_decision_detected(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    write_jsonl(decisions, [])
    with pytest.raises(ValueError, match='Missing decisions'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)


def test_invalid_calendar_date_rejected(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    row = sign(read_jsonl(decisions)[0]); row['reviewed_at'] = '2026-02-30'
    write_jsonl(decisions, [row])
    with pytest.raises(ValueError, match='invalid reviewed_at'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)


def test_review_template_does_not_destroy_manual_work(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    decision = read_jsonl(decisions)[0]
    decision.update(decision='approve', reviewer='QA Reviewer', reviewed_at='2026-10-23',
                    review_note='Verified manually against the original document evidence.')
    write_jsonl(decisions, [decision])
    with pytest.raises(FileExistsError, match='refusing to overwrite human work'):
        review_template(tmp_path, candidates, registry, holds, decisions, coverage)
    assert read_jsonl(decisions)[0]['decision'] == 'approve'


def test_finalize_does_not_overwrite_previous_approved_work(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    write_jsonl(decisions, [sign(read_jsonl(decisions)[0])])
    finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    first = output.read_bytes()
    with pytest.raises(FileExistsError, match='refusing to overwrite'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
    assert first == output.read_bytes()


def test_decision_provenance_cannot_be_edited(tmp_path):
    _, _, _, (candidates, registry, holds, decisions, output, coverage) = start(tmp_path)
    row = sign(read_jsonl(decisions)[0]); row['as_of_year'] = 2024
    write_jsonl(decisions, [row])
    with pytest.raises(ValueError, match='cannot change candidate provenance'):
        finalize_review(tmp_path, candidates, decisions, registry, holds, output, coverage)
