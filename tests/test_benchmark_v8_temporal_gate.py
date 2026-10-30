"""V8 temporal audit regressions; sources are repo-local and never released."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'scripts/benchmark_v8_temporal_gate.py'


def module():
    spec = importlib.util.spec_from_file_location('v8_temporal', GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def test_v8_preview_is_review_only_and_has_90_rows():
    r = module().inspect(ROOT)
    assert r['status'] == 'REVIEW_REQUIRED'
    assert r['rows'] == 90
    assert r['changed_ids'] == 12
    assert r['temporal_causality_fixed_in_preview'] == 6
    assert not r['benchmark_frozen']
    assert not r['training_authorized']


def test_all_six_retro_cases_ineligible_before_2026():
    v8 = {r['id']: r for r in read(ROOT / 'docs/benchmark_review_v8/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl')}
    retro = module().RETRO
    assert len(retro) == 6
    for rid, historical in retro.items():
        assert v8[rid]['retrospective_subject_year'] == historical
        assert v8[rid]['as_of_year'] == 2026
        assert not (v8[rid]['as_of_year'] <= 2025)
        assert v8[rid]['as_of_year'] <= 2026


def test_candidate_keeps_90_and_all_categories_and_gold_aliases():
    candidate = read(ROOT / 'docs/benchmark_review_v8/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl')
    assert len(candidate) == len({r['id'] for r in candidate}) == 90
    assert {name: sum(x['category'] == name for x in candidate) for name in ('active_rule', 'superseded_rule', 'temporal_specific')} == {
        'active_rule': 37, 'superseded_rule': 27, 'temporal_specific': 26}
    assert all(r['gold_answer'] == r['ground_truth_answer'] and r['gold_doc_id'] == r['source_doc_id'] and r['as_of_year'] == r['target_year'] for r in candidate)


def test_foreign_tuition_2024_supporting_source_present():
    r = next(r for r in read(ROOT / 'docs/benchmark_review_v8/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl') if r['id'] == 'BENCH_SUP_012')
    docs = r['supporting_sources']
    assert len(docs) == 1
    assert docs[0]['source_sha256'] == '3ad05a22390d4729d416bc6a9d84dc2030aae9291e043db4b884ea3a8d0f76b1'


def test_rejects_modified_artifact(tmp_path):
    (tmp_path/'data/qa_benchmark').mkdir(parents=True)
    (tmp_path/'docs/benchmark_review_v7/review_only').mkdir(parents=True)
    (tmp_path/'docs/benchmark_review_v8').mkdir(parents=True)
    shutil.copyfile(ROOT/'data/qa_benchmark/benchmark.jsonl',tmp_path/'data/qa_benchmark/benchmark.jsonl')
    shutil.copyfile(ROOT/'docs/benchmark_review_v7/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl',tmp_path/'docs/benchmark_review_v7/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl')
    shutil.copytree(ROOT/'docs/benchmark_review_v8',tmp_path/'docs/benchmark_review_v8',dirs_exist_ok=True)
    v8=tmp_path/'docs/benchmark_review_v8/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl'
    v8.write_text(v8.read_text(encoding='utf-8').replace('BENCH_SUP_001', 'BENCH_SUP_XXX',1),encoding='utf-8')
    with pytest.raises(ValueError):module().inspect(tmp_path)


def test_gate_command_returns_review_not_release():
    p=subprocess.run([sys.executable,str(GATE),'--repo',str(ROOT)],text=True,capture_output=True,encoding='utf-8',check=False)
    assert p.returncode == 2
    payload=json.loads(p.stdout)
    assert payload['status']=='REVIEW_REQUIRED'
    assert payload['training_authorized'] is False
