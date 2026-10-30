import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import pytest

P=Path(__file__).resolve().parents[1]/'scripts/benchmark_content_provenance_gate_v6.py'
spec=importlib.util.spec_from_file_location('v6_gate', P)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_amount_detection_and_multisource():
    sources={'a':'Mức 1.850.000 đồng', 'b':'Mức 2.090.000 đồng'}
    rows=[{'id':'X','source_sha256':'a', 'gold_answer':'Từ 1.850.000 thành 2.090.000'}]
    observed=gate.audit_rows(rows,sources)
    assert observed[0]['status']=='NEEDS_MULTIPLE_DOCUMENTS'
    assert observed[0]['missing_primary_amounts']==['2.090.000']


def test_unsupported_numeric_discrepancy():
    data=gate.audit_rows([{'id':'X', 'source_sha256':'a','gold_answer':'870.000'}],{'a':'869.000'})
    assert data[0]['status']=='UNSUPPORTED_AMOUNT_IN_22_SOURCE_SET'


def test_duplicate_and_malformed_registry(tmp_path):
    file=tmp_path/'refs.csv'
    with file.open('w',newline='',encoding='utf8') as f:
        wr=csv.DictWriter(f,['doc_id','source_sha256','local_paths']);wr.writeheader()
        for i in range(22):wr.writerow({'doc_id':'duplicate','source_sha256':str(i),'local_paths':'x'})
    with pytest.raises(ValueError,match='unique'):gate.read_references(file)


def test_expected_real_ids_are_present_in_review():
    import csv
    csv_path=Path(__file__).resolve().parents[1]/'docs/benchmark_review_v6/amount_provenance_90.csv'
    rows=list(csv.DictReader(csv_path.open(encoding='utf8')))
    assert len(rows)==90
    exception_ids={r['benchmark_id'] for r in rows if r['missing_primary_amounts']}
    assert exception_ids=={'BENCH_SUP_001','BENCH_SUP_002','BENCH_SUP_003',
                            'BENCH_SUP_008','BENCH_SUP_012','BENCH_SUP_021'}


def test_review_proposals_remain_unapproved():
    path=Path(__file__).resolve().parents[1]/'docs/benchmark_review_v6/proposed_changes_10_NOT_APPLIED.jsonl'
    proposals=[json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert len(proposals)==10
    assert all(p['decision']=='PENDING_REVIEW' for p in proposals)
    assert {p['id'] for p in proposals}>= {'BENCH_SUP_008','BENCH_SUP_012'}


def test_no_authorization_code():
    source=P.read_text(encoding="utf-8")
    assert "'benchmark_frozen': False" in source
    assert "'training_authorized': False" in source
    assert 'return 2' in source
