"""Regression checks for provisional benchmark V7 preview (no trainer)."""
import csv
import hashlib
import json
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]/'docs'/'benchmark_review_v7'
DATA = ROOT / "review_only"
EXPECTED_SHA = '333404a93e510ca580a19dc149c2f93587782eb6380def40626deaa05e1036e2'
EXPECTED_CHANGED = {'BENCH_SUP_008','BENCH_SUP_012','BENCH_SUP_001','BENCH_SUP_002','BENCH_SUP_003','BENCH_SUP_021','BENCH_TEM_001','BENCH_TEM_002','BENCH_TEM_005','BENCH_TEM_006'}
FILENAMES = ['benchmark_candidate_90_NOT_FROZEN.jsonl','valid_candidate_37_NOT_FROZEN.jsonl','superseded_candidate_27_NOT_FROZEN.jsonl','year_specific_candidate_26_NOT_FROZEN.jsonl']

def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def test_manifest_restricted():
    m = json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
    assert m['source_primary_sha256'] == EXPECTED_SHA
    assert m['status'] == 'REVIEW_ONLY_NOT_FROZEN_NOT_FOR_MODEL_EVALUATION'
    assert m['benchmark_frozen'] is False and m['owner_approved'] is False and m['training_authorized'] is False
    for v in m['candidate_files'].values():
        p = ROOT/v['file']
        assert hashlib.sha256(p.read_bytes()).hexdigest() == v['sha256']
        assert len(rows(p)) == v['rows']

def test_primary_ids_and_splits():
    full,valid,sup,tem = [rows(DATA/x) for x in FILENAMES]
    assert [len(s) for s in [full,valid,sup,tem]] == [90,37,27,26]
    assert len({r['id'] for r in full}) == 90
    assert {r['id'] for r in full} == set().union(*({r['id'] for r in rs} for rs in [valid,sup,tem]))
    byid = {r['id']:r for r in full}
    for r in full:
        assert r['gold_answer'] == r['ground_truth_answer']
        assert r['gold_doc_id'] == r['source_doc_id']
        assert r['target_year'] == r['as_of_year']
        assert r['type'] == r['category']
    for group in [valid,sup,tem]:
        for r in group:
            for k,v in r.items():
                assert byid[r['id']][k] == v

def test_delta_only_ten():
    delta = rows(DATA/'proposed_delta_10.jsonl')
    assert len(delta) == 10
    assert {r['id'] for r in delta} == EXPECTED_CHANGED
    assert all(r['decision']=='PENDING_OWNER_REVIEW' for r in delta)
    old_hashes=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))['original_record_sha256_by_id']
    now={r['id']:r for r in rows(DATA/FILENAMES[0])}
    assert set(old_hashes)==set(now)
    computed={id:hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for id,r in now.items()}
    assert {id for id in now if computed[id] != old_hashes[id]}==EXPECTED_CHANGED
    assert all(computed[id]==old_hashes[id] for id in now if id not in EXPECTED_CHANGED)


def test_specific_content_corrections():
    byid={r['id']:r for r in rows(DATA/FILENAMES[0])}
    p=byid['BENCH_SUP_008']
    assert '869.000' in p['gold_answer'] and '870.000' not in p['gold_answer']
    assert 'Trí tuệ nhân tạo' in p['question'] and 'CNTT' not in p['question']
    assert 'Điều 3' in p['source_clause']
    q=byid['BENCH_SUP_012']
    assert '996.000' not in q['question']+q['gold_answer']
    assert 'QH-2021' in q['gold_answer']

def test_temporal_and_supporting_sources():
    byid={r['id']:r for r in rows(DATA/FILENAMES[0])}
    for id in ['BENCH_TEM_001','BENCH_TEM_002','BENCH_TEM_005','BENCH_TEM_006']:
        assert '16/05/2022' in byid[id]['question']
        assert 'amendment_source_url' in byid[id]
    for id in ['BENCH_SUP_001','BENCH_SUP_002','BENCH_SUP_003','BENCH_SUP_021']:
        assert byid[id]['supporting_sources']
        for x in byid[id]['supporting_sources']:
            assert len(x['source_sha256'])==64 and x['official_source_url'].startswith('https://')
