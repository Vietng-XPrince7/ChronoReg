"""Offline, deterministic safeguards for table-draft quality audit."""
import csv
import hashlib

import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.review import candidate_fingerprint
from src.lora.table_audit import audit_tables
from src.lora.table_candidates import propose_tables


def _fixture(tmp_path, bad_cell='I.1', section='# TEST 2026'):
    source = tmp_path / 'data/raw/uet/markdown/2026/tuition.md'
    source.parent.mkdir(parents=True)
    source.write_text(
        f'{section}\n\n'
        '| TT | Khóa tuyển sinh / chương trình | Học phí (đồng/tháng) |\n'
        '|---|---|---:|\n'
        f'| {bad_cell} | Khóa QH-2026 | 2.150.000 |\n', encoding='utf-8'
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    registry = tmp_path / 'data/versioning/documents.jsonl'
    holds = tmp_path / 'data/versioning/publication_holds.jsonl'
    write_jsonl(registry, [dict(
        doc_id='uet-test-2026', relative_path='2026/tuition.md',
        content_sha256=digest, topic_hint='tuition',
        academic_year_verified='2026-2027',
        review_status='verified_against_source', policy_qa_ready=True,
    )])
    write_jsonl(holds, [])
    candidates = tmp_path / 'drafts.jsonl'
    audit = tmp_path / 'audit.csv'
    return source, registry, holds, candidates, audit


def test_generator_skips_identifier_column(tmp_path):
    _, registry, holds, candidates, _ = _fixture(tmp_path)
    report = propose_tables(tmp_path, registry, holds, candidates)
    assert report['candidates'] == 1
    rows = read_jsonl(candidates)
    assert rows[0]['answer'] == '2.150.000'
    assert rows[0]['table_column'] == 'Học phí (đồng/tháng)'


def test_audit_pending_and_provenance_report(tmp_path):
    _, registry, holds, candidates, audit = _fixture(tmp_path)
    propose_tables(tmp_path, registry, holds, candidates)
    before = candidates.read_bytes()
    report = audit_tables(tmp_path, candidates, registry, holds, audit)
    assert report['audited_candidates'] == 1 and report['approved'] == 0
    assert report['requires_rewrite'] == 0
    with audit.open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['risk_flags'] == 'SOURCE_PDF_REVIEW_REQUIRED'
    assert row['candidate_sha256'] == candidate_fingerprint(read_jsonl(candidates)[0])
    assert candidates.read_bytes() == before


def test_flags_legacy_identifier_answer(tmp_path):
    _, registry, holds, candidates, audit = _fixture(tmp_path)
    propose_tables(tmp_path, registry, holds, candidates)
    rows = read_jsonl(candidates)
    rows[0]['answer'] = 'I.1'
    rows[0]['table_column'] = 'TT'
    write_jsonl(candidates, rows)
    result = audit_tables(tmp_path, candidates, registry, holds, audit)
    assert result['requires_rewrite'] == 1
    assert result['flags']['IDENTIFIER_COLUMN'] == 1
    assert result['flags']['NON_MONETARY_VALUE'] == 1


def test_generic_section_flagged(tmp_path):
    _, registry, holds, candidates, audit = _fixture(
        tmp_path, section='# TRƯỜNG ĐẠI HỌC CÔNG NGHỆ QUYẾT ĐỊNH:')
    propose_tables(tmp_path, registry, holds, candidates)
    report = audit_tables(tmp_path, candidates, registry, holds, audit)
    assert report['flags']['GENERIC_SECTION'] == 1
    assert report['requires_rewrite'] == 1


def test_audit_never_overwrites(tmp_path):
    _, registry, holds, candidates, audit = _fixture(tmp_path)
    propose_tables(tmp_path, registry, holds, candidates)
    audit.write_bytes(b'KEEP')
    with pytest.raises(FileExistsError):
        audit_tables(tmp_path, candidates, registry, holds, audit)
    assert audit.read_bytes() == b'KEEP'


def test_source_change_aborts_before_writing(tmp_path):
    source, registry, holds, candidates, audit = _fixture(tmp_path)
    propose_tables(tmp_path, registry, holds, candidates)
    source.write_text(source.read_text(encoding='utf-8')+'CHANGED', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA mismatch'):
        audit_tables(tmp_path, candidates, registry, holds, audit)
    assert not audit.exists()


def test_benchmark_exact_overlap_flagged_without_modifying_it(tmp_path):
    _, registry, holds, candidates, audit = _fixture(tmp_path)
    propose_tables(tmp_path, registry, holds, candidates)
    draft = read_jsonl(candidates)[0]
    benchmark = tmp_path/'benchmark.jsonl'
    write_jsonl(benchmark, [dict(id='eval-only', question=draft['question'],
                                 gold_answer='2.150.000', gold_doc_id=draft['doc_id'],
                                 type='current', as_of_year=2026)])
    original = benchmark.read_bytes()
    report = audit_tables(tmp_path, candidates, registry, holds, audit, benchmark)
    assert report['requires_rewrite'] == 1
    assert report['flags']['BENCHMARK_EXACT_QUESTION'] == 1
    assert benchmark.read_bytes() == original


def test_spreadsheet_formula_sanitized(tmp_path):
    _, registry, holds, candidates, audit = _fixture(tmp_path)
    propose_tables(tmp_path, registry, holds, candidates)
    rows = read_jsonl(candidates)
    rows[0]['table_section'] = '=HYPERLINK("http://example.invalid")'
    write_jsonl(candidates, rows)
    audit_tables(tmp_path, candidates, registry, holds, audit)
    with audit.open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['table_section'].startswith("'=")
