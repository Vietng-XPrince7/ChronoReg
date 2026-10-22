"""Source-bound consistency tests for UET review batch 2 (metadata only)."""
from pathlib import Path
from src.versioning.core import read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def test_review_batch_2_scope_and_years(tmp_path):
    docs = read_jsonl(ROOT / 'data/versioning/reviewed_documents.jsonl')
    assert len(docs) >= 6
    assert len({d['doc_id'] for d in docs}) == 6
    hb26 = next(d for d in docs if d['doc_id'].startswith('uet-2026-quy-dinh-xet-hoc-bong'))
    assert hb26['academic_year'] == '2026-2027'
    assert hb26['effective_from'] == '2026-08-07'
    assert hb26['effective_until_exclusive'] is None
    assert not hb26['open_ended_verified']
    policy24 = next(d for d in docs if d['doc_id'].startswith('uet-2024-quy-dinh-ve-hoc-bong'))
    assert policy24['academic_year'] is None
    assert policy24['effective_from'] == '2024-10-07'
    assert not policy24['open_ended_verified']
