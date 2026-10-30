import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pytest

CODE=Path(__file__).parents[1]/'scripts'/'benchmark_freeze_readiness_gate.py'
spec=importlib.util.spec_from_file_location('gate',CODE)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
REVIEW=Path(__file__).parents[1]/'docs'/'benchmark_review'

def test_gate_is_read_only_and_fails_closed_for_missing_repo(tmp_path):
    with pytest.raises(ValueError,match='Primary benchmark missing'):
        gate.check(tmp_path,REVIEW)
    assert not list(tmp_path.iterdir())

def test_checksum_known_vector(tmp_path):
    p=tmp_path/'x';p.write_bytes(b'test')
    assert gate.fingerprint(p)=='9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'

def test_review_package_self_consistent():
    corrections=gate.read_csv(REVIEW/'correction_review_42.csv')
    docs=gate.read_csv(REVIEW/'source_registry_24.csv')
    temporal=gate.read_csv(REVIEW/'benchmark_temporal_registry_90.csv')
    assert len(corrections)==42 and len({x['benchmark_id'] for x in corrections})==42
    assert len(docs)==24 and sum(int(x['item_count']) for x in docs)==90
    assert len(temporal)==90 and len({x['benchmark_id'] for x in temporal})==90
    assert all(x['owner_acceptance']=='PENDING' for x in corrections)
    assert all(x['evaluation_safety']=='PROVISIONAL_NOT_FROZEN' for x in temporal)

def test_temporal_amendment_items_preserved():
    changes=gate.read_jsonl(REVIEW/'proposed_temporal_question_changes_4_NOT_APPLIED.jsonl')
    assert {x['id'] for x in changes}=={'BENCH_TEM_001','BENCH_TEM_002','BENCH_TEM_005','BENCH_TEM_006'}
    assert all(x['gold_answer_changed'] is False and x['status']=='DRAFT_NOT_APPLIED' for x in changes)

def test_production_benchmark_when_available():
    repo_path=os.getenv('CHRONOREG_REPO')
    if not repo_path:
        pytest.skip('Set CHRONOREG_REPO to run the actual repository integration test.')
    result=gate.check(Path(repo_path),REVIEW)
    assert result['primary_rows']==90 and result['review_corrections']==42
    assert not result['benchmark_frozen'] and not result['training_authorized']
    assert 'FOUR_RETROSPECTIVE_TUITION_QUESTIONS_UNRESOLVED_IN_PRIMARY' in result['blocking_reasons']
