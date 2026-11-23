"""Read-only checks for canonical UET curricula and safe deduplication."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rebuild_curricula_catalog import build_catalog  # noqa: E402


def test_catalog_has_no_duplicate_content_or_ids():
    expected = json.loads((ROOT / 'data/raw/uet/curricula/catalog.json').read_text(encoding='utf-8'))
    actual = build_catalog(ROOT)
    assert actual == expected
    assert len(actual['records']) == 84
    assert len({item['doc_id'] for item in actual['records']}) == 84
    assert len({item['content_sha256'] for item in actual['records']}) == 84
    assert sum(item['collection'] == 'official_uet_extractions' for item in actual['records']) == 31
    assert sum(item['collection'] == 'team_original_uploads' for item in actual['records']) == 53
    assert all(item['retrieval_eligible'] is False for item in actual['records'])


def test_preserved_sources_and_paths_match_sha256():
    catalog = build_catalog(ROOT)
    for doc in catalog['records']:
        raw = (ROOT / doc['content_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == doc['content_sha256']
        assert doc['content_path'].endswith('.md')
    excluded = catalog['excluded_documents']
    assert len(excluded) == 1
    assert hashlib.sha256((ROOT / excluded[0]['original_path']).read_bytes()).hexdigest() == excluded[0]['original_sha256']


def test_removed_copies_are_exactly_documented_and_absent():
    report = json.loads((ROOT / 'data/raw/uet/curricula/DEDUP_EVIDENCE.json').read_text(encoding='utf-8'))
    assert report['duplicated_normalized_body_replicas_removed'] == 53
    pairs = report['deduplicated_pairs']
    assert len(pairs) == 53
    assert len({p['removed_duplicate_path'] for p in pairs}) == 53
    for p in pairs:
        assert p['body_byte_equal_original'] is True
        assert not (ROOT / p['removed_duplicate_path']).exists()
        assert hashlib.sha256((ROOT / p['retained_content_path']).read_bytes()).hexdigest() == p['original_body_sha256']


def test_important_distinct_versions_are_retained():
    docs = {item['doc_id']: item for item in build_catalog(ROOT)['records']}
    ids = ('uet-curriculum-artificial-intelligence-QH-2022-to-2024-original',
           'uet-curriculum-artificial-intelligence-QH-2022-to-2024-updated')
    assert all(doc_id in docs for doc_id in ids)
    assert docs[ids[0]]['content_sha256'] != docs[ids[1]]['content_sha256']
    assert docs[ids[0]]['edition'] != docs[ids[1]]['edition']


def test_unsafe_catalog_path_rejected(tmp_path):
    from rebuild_curricula_catalog import check_relative_path
    with pytest.raises(ValueError, match='NON_CANONICAL_PATH'):
        check_relative_path(tmp_path, '../outside.md')
    with pytest.raises(ValueError, match='CONTENT_MISSING'):
        check_relative_path(tmp_path, 'missing.md')


def test_human_readable_index_opens_full_markdown_not_just_web_links():
    root = ROOT / 'data/raw/uet'
    index = (root / 'markdown/curricula/INDEX.md').read_text(encoding='utf-8')
    manifest = json.loads((root / 'curricula/manifest.json').read_text(encoding='utf-8'))
    for record in manifest['records']:
        expected_local = f"[{record['edition_label']}](./{record['doc_id']}.md)"
        assert expected_local in index, record['doc_id']
    assert len(manifest['records']) == 31


def test_source_cards_are_never_canonical_content():
    catalog = build_catalog(ROOT)
    for record in catalog['records']:
        assert '/source_cards/' not in record['content_path']
        assert not record['content_path'].startswith('http')
        if record['source_card_path']:
            assert '/source_cards/' in record['source_card_path']
            assert (ROOT / record['source_card_path']).is_file()


def test_five_distinct_original_curricula_not_lost_during_branch_reconciliation():
    root = ROOT / 'data/raw/uet/curricula/tuan_2022_2026/original'
    required = (
        'chuan_dau_ra_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md',
        'chuan_dau_ra_chuong_trinh_dao_tao_cntt_nhat_ban_2022_tro_di.md',
        'gioi_thieu_chung_ve_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md',
        'gioi_thieu_chung_ve_chuong_trinh_dao_tao_cntt_nhat_ban_2022_tro_di.md',
        'noi_dung_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md',
    )
    assert all((root / name).is_file() for name in required)
    hashes = {hashlib.sha256((root / name).read_bytes()).hexdigest() for name in required}
    assert len(hashes) == len(required)
