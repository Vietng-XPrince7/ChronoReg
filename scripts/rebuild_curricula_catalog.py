#!/usr/bin/env python3
"""Generate/check the single content locator for UET curricula.

The full-text source of truth remains original MD or UET-extracted MD.
This catalog is a deterministic index, not a new content copy or a review approval.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT_REL = Path('data/raw/uet/curricula')
CATALOG_REL = ROOT_REL / 'catalog.json'
CURR_MD_REL = Path('data/raw/uet/markdown/curricula')


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_relative_path(root: Path, rel: str) -> Path:
    if not rel or Path(rel).is_absolute() or '..' in Path(rel).parts:
        raise ValueError(f'NON_CANONICAL_PATH: {rel!r}')
    target = root / rel
    if not target.is_file():
        raise ValueError(f'CONTENT_MISSING: {rel}')
    return target


def build_catalog(root: Path) -> dict:
    base = root / ROOT_REL
    site_manifest = load_json(base / 'manifest.json')
    tuan_manifest = load_json(base / 'tuan_2022_2026/manifest.json')
    checks = load_json(base / 'source_checksums.json')
    results = []
    doc_ids = set()
    content_checksums = set()
    if len(site_manifest['records']) != 31:
        raise ValueError('EXPECTED_31_OFFICIAL_SITE_RECORDS')
    if len(tuan_manifest['documents']) != 49:
        raise ValueError('EXPECTED_49_ACTIVE_UPLOAD_RECORDS')
    excluded_by_owner = tuan_manifest.get('owner_excluded_documents', [])
    if (len(excluded_by_owner) != 5 or
            tuan_manifest.get('owner_excluded_original_records') != 5 or
            tuan_manifest.get('active_unique_source_records') != 49 or
            len(tuan_manifest['documents']) + len(excluded_by_owner) != tuan_manifest['unique_source_records']):
        raise ValueError('OWNER_EXCLUSION_HISTORY_INCONSISTENT')
    expected_removed_names = {
        'chuan_dau_ra_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md',
        'chuan_dau_ra_chuong_trinh_dao_tao_cntt_nhat_ban_2022_tro_di.md',
        'gioi_thieu_chung_ve_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md',
        'gioi_thieu_chung_ve_chuong_trinh_dao_tao_cntt_nhat_ban_2022_tro_di.md',
        'noi_dung_chuong_trinh_dao_tao_cntt_clc_2022_tro_di.md',
    }
    if {x['file_name'] for x in excluded_by_owner} != expected_removed_names:
        raise ValueError('UNEXPECTED_OWNER_EXCLUDED_FILES')
    remaining_doc_ids = {x['doc_id'] for x in tuan_manifest['documents']}
    for item in excluded_by_owner:
        if item['doc_id'] in remaining_doc_ids:
            raise ValueError(f'EXCLUDED_DOC_STILL_ACTIVE: {item["doc_id"]}')
        if (root / item['source_path']).exists():
            raise ValueError(f'EXCLUDED_ORIGINAL_STILL_PRESENT: {item["source_path"]}')
    original_dir = base / 'tuan_2022_2026/original'
    actual_originals = {p.name for p in original_dir.glob('*.md')}
    expected_originals = {x['file_name'] for x in tuan_manifest['documents']}
    if actual_originals != expected_originals:
        raise ValueError(f'ACTIVE_ORIGINAL_SET_MISMATCH: {sorted(actual_originals ^ expected_originals)}')
    # Historical ZIP occurrence counts are immutable dedup provenance.
    if (tuan_manifest['source_records'] !=
            tuan_manifest['unique_source_records'] + tuan_manifest['duplicate_archive_occurrences']):
        raise ValueError('ARCHIVE_OCCURRENCE_COUNTS_INCONSISTENT')
    if (tuan_manifest['curriculum_records'] != 48 or
            tuan_manifest['excluded_non_curriculum_records'] != 1):
        raise ValueError('UPLOAD_MANIFEST_RECORD_COUNTS_INCONSISTENT')

    for record in site_manifest['records']:
        doc_id = record['doc_id']
        path = record['content_md_path']
        card_path = record['source_card_path']
        if path != (CURR_MD_REL / (doc_id + '.md')).as_posix():
            raise ValueError(f'OFFICIAL_CONTENT_PATH_INCONSISTENT: {doc_id}')
        if card_path != (CURR_MD_REL / 'source_cards' / (doc_id + '.md')).as_posix():
            raise ValueError(f'SOURCE_CARD_PATH_INCONSISTENT: {doc_id}')
        data = check_relative_path(root, path).read_bytes()
        check_relative_path(root, card_path)
        digest = sha256(data)
        if digest != checks[doc_id]['sha256_markdown'] or checks[doc_id]['output_md_path'] != path:
            raise ValueError(f'OFFICIAL_CHECKSUM_MISMATCH: {doc_id}')
        if record['retrieval_eligible'] is not False:
            raise ValueError(f'UNAPPROVED_DOC_ENABLED: {doc_id}')
        if doc_id in doc_ids or digest in content_checksums:
            raise ValueError(f'DUPLICATE_OFFICIAL_ID_OR_CONTENT: {doc_id}')
        doc_ids.add(doc_id)
        content_checksums.add(digest)
        results.append({
            'doc_id': doc_id,
            'collection': 'official_uet_extractions',
            'content_path': path,
            'content_sha256': digest,
            'content_kind': record['curriculum_status'],
            'program_identifier': record['program_slug'],
            'program_identifier_status': 'official_index_metadata',
            'cohort_from': record['cohort_from'],
            'cohort_to': record['cohort_to'],
            'cohort_hint_unverified': None,
            'edition': record['edition_label'],
            'source_url': record['source_index_url'],
            'source_card_path': card_path,
            'manifest_path': ROOT_REL.joinpath('manifest.json').as_posix(),
            'review_status': record['review_status'],
            'retrieval_eligible': False,
        })

    excluded = []
    for record in tuan_manifest['documents']:
        doc_id = record['doc_id']
        path = record.get('content_md_path')
        original = record['source_path']
        original_sha = record['source_sha256']
        if sha256(check_relative_path(root, original).read_bytes()) != original_sha:
            raise ValueError(f'TUAN_SOURCE_CHECKSUM_MISMATCH: {doc_id}')
        if record['retrieval_eligible'] is not False:
            raise ValueError(f'UNAPPROVED_UPLOAD_ENABLED: {doc_id}')
        if record.get('normalized_path') is not None:
            raise ValueError(f'STALE_NORMALIZED_COPY_REFERENCE: {doc_id}')
        if record['kind'] == 'admissions_guidance':
            if path is not None or record.get('content_sha256') is not None:
                raise ValueError(f'OUT_OF_SCOPE_MARKED_AS_CURRICULUM: {doc_id}')
            excluded.append({'doc_id': doc_id, 'original_path': original,
                             'original_sha256': original_sha,
                             'reason': 'admissions_guidance_not_curriculum'})
            continue
        if path != original or record.get('content_sha256') != original_sha:
            raise ValueError(f'TUAN_CANONICAL_PATH_MISMATCH: {doc_id}')
        digest = sha256(check_relative_path(root, path).read_bytes())
        if doc_id in doc_ids or digest in content_checksums:
            raise ValueError(f'DUPLICATE_CURRICULUM_ID_OR_CONTENT: {doc_id}')
        doc_ids.add(doc_id)
        content_checksums.add(digest)
        results.append({
            'doc_id': doc_id,
            'collection': 'team_original_uploads',
            'content_path': path,
            'content_sha256': digest,
            'content_kind': record['kind'],
            'program_identifier': record['program_hint'],
            'program_identifier_status': 'filename_hint_only',
            'cohort_from': None,
            'cohort_to': None,
            'cohort_hint_unverified': record['cohort_hint'],
            'edition': None,
            'source_url': record['official_source_url'],
            'source_card_path': None,
            'manifest_path': ROOT_REL.joinpath('tuan_2022_2026/manifest.json').as_posix(),
            'review_status': record['review_status'],
            'retrieval_eligible': False,
        })

    if len(results) != 79 or len(excluded) != 1:
        raise ValueError('CATALOG_COUNTS_MISMATCH')
    expected_file_names = {r['doc_id'] + '.md' for r in site_manifest['records']}
    listed_file_names = {p.name for p in (root / CURR_MD_REL).glob('uet-curriculum-*.md')}
    if expected_file_names != listed_file_names:
        raise ValueError(f'OFFICIAL_ORPHAN_OR_MISSING_MARKDOWN: {sorted(expected_file_names ^ listed_file_names)}')
    # Restored legacy wrappers are compatibility copies, never canonical catalog entries.
    evidence = load_json(base / 'DEDUP_EVIDENCE.json')
    pairs = evidence['deduplicated_pairs']
    expected_wrappers = {p['removed_duplicate_path']: p['removed_wrapper_sha256'] for p in pairs}
    actual_wrappers = {p.relative_to(root).as_posix(): sha256(p.read_bytes())
                       for p in (root / CURR_MD_REL / 'tuan_2022_2026').glob('*.md')}
    if len(expected_wrappers) != 53 or actual_wrappers != expected_wrappers:
        raise ValueError('RESTORED_LEGACY_WRAPPERS_MISSING_OR_CHANGED')
    recorded_site = {r['doc_id']: r for r in csv.DictReader((base / 'versions.csv').open(encoding='utf-8-sig', newline=''))}
    recorded_tuan = {r['doc_id']: r for r in csv.DictReader((base / 'tuan_2022_2026/versions.csv').open(encoding='utf-8-sig', newline=''))}
    if set(recorded_site) != {r['doc_id'] for r in site_manifest['records']}:
        raise ValueError('SITE_VERSIONS_MANIFEST_IDS_DIFFER')
    if set(recorded_tuan) != {r['doc_id'] for r in tuan_manifest['documents']}:
        raise ValueError('TUAN_VERSIONS_MANIFEST_IDS_DIFFER')
    for record in site_manifest['records']:
        row = recorded_site[record['doc_id']]
        if row.get('content_md_path') != record['content_md_path'] or row.get('source_card_path') != record['source_card_path']:
            raise ValueError(f'SITE_VERSIONS_PATH_MISMATCH: {record["doc_id"]}')
        if row.get('retrieval_eligible') != 'False':
            raise ValueError(f'SITE_VERSIONS_RETRIEVAL_ENABLED: {record["doc_id"]}')
    for record in tuan_manifest['documents']:
        row = recorded_tuan[record['doc_id']]
        if row.get('content_md_path') != (record['content_md_path'] or ''):
            raise ValueError(f'TUAN_VERSIONS_PATH_MISMATCH: {record["doc_id"]}')
        if row.get('retrieval_eligible') != 'False':
            raise ValueError(f'TUAN_VERSIONS_RETRIEVAL_ENABLED: {record["doc_id"]}')

    results.sort(key=lambda r: (r['collection'], r['program_identifier'], r['doc_id']))
    return {
        'schema_version': '1.0',
        'purpose': 'One content locator for UET curricula, no duplicated full-text payloads',
        'scope': 'UET QH-2022 to QH-2026; not the full set of UET regulations',
        'official_site_extractions': 31,
        'team_original_curriculum_sections': 48,
        'owner_excluded_original_sections': 5,
        'archived_unique_upload_records': 54,
        'canonical_content_count': len(results),
        'non_curriculum_excluded_count': len(excluded),
        'retrieval_eligibility_policy': 'human_review_required; all false at this snapshot',
        'records': results,
        'excluded_documents': excluded,
        'owner_excluded_documents': excluded_by_owner,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, default=Path('.'))
    ap.add_argument('--write', action='store_true', help='Write a deterministic catalog based on manifests and original bytes.')
    ap.add_argument('--check', action='store_true', help='Require the catalog to match manifests and actual file bytes.')
    args = ap.parse_args()
    if args.write == args.check:
        ap.error('Specify exactly one of --write or --check.')
    root = args.repo.resolve()
    result = build_catalog(root)
    path = root / CATALOG_REL
    expected = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.write:
        path.write_text(expected, encoding='utf-8')
    elif not path.is_file() or path.read_text(encoding='utf-8') != expected:
        raise ValueError('CATALOG_STALE: run scripts/rebuild_curricula_catalog.py --write')
    print(json.dumps({'status': 'PASS' if args.check else 'WRITTEN',
                      'canonical_content_count': result['canonical_content_count'],
                      'official_site_extractions': result['official_site_extractions'],
                      'team_original_curriculum_sections': result['team_original_curriculum_sections'],
                      'excluded_non_curriculum': result['non_curriculum_excluded_count']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, AssertionError) as error:
        print(f'CURRICULA_CATALOG_FAILED: {error}', file=sys.stderr)
        sys.exit(2)
