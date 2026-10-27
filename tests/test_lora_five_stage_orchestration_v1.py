"""GPU-free tests for release-bound five-stage orchestration."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from src.lora import run_five_stages as run

SHA = 'a' * 40
YEARS = [2022, 2023, 2024, 2025, 2026]


def fixture(tmp_path, monkeypatch):
    root = tmp_path
    (root / 'configs').mkdir()
    cfg = {'base_model': 'Qwen/Qwen2.5-0.5B-Instruct', 'model_revision': SHA,
           'strategy': 'sequential', 'model_dtype': 'float32', 'max_seq_length': 512,
           'years': YEARS}
    (root / 'configs/lora.yaml').write_text(yaml.safe_dump({'lora': cfg}), encoding='utf-8')
    (root / 'data/qa_benchmark').mkdir(parents=True)
    bench = root / 'data/qa_benchmark/benchmark.jsonl'
    bench.write_text('real heldout placeholder for mocked evaluation\n', encoding='utf-8')
    prepared = root / 'prepared'; prepared.mkdir()
    manifest = {'years': YEARS, 'total': 5, 'counts': {}, 'year_sha256': {}}
    for y in YEARS:
        p = prepared / f'train_{y}.jsonl'
        p.write_text(f'{{"year":{y}}}\n', encoding='utf-8')
        manifest['counts'][str(y)] = 1
        manifest['year_sha256'][str(y)] = run.sha256(p)
    (prepared / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    token = root / 'release.json'; token.write_text('{"status":"fixture"}', encoding='utf-8')
    calls = []
    def authorized(repo, prepared_dir, year, release):
        calls.append(year)
        return {'release_file_sha256': run.sha256(token),
                'benchmark_sha256': run.sha256(bench)}
    monkeypatch.setattr(run, 'require_training_release', authorized)
    return root, cfg, token, prepared, root/'checkpoints', root/'results', calls, manifest


def save_checkpoint(root, ckpts, y, cfg, manifest, release, *, integrity=True):
    p = ckpts / f'year-{y}'; p.mkdir(parents=True)
    (p / 'adapter_model.safetensors').write_bytes(b'synthetic-test-adapter')
    (p / 'adapter_config.json').write_text('{}', encoding='utf-8')
    (p / 'stage.json').write_text(json.dumps({'year':y, 'model':cfg['base_model'],
       'model_revision':cfg['model_revision'], 'model_dtype':cfg['model_dtype'],
       'training_sha256':manifest['year_sha256'][str(y)], 'strategy':'sequential',
       'release_evidence':{'release_file_sha256':run.sha256(release)}}), encoding='utf-8')
    if integrity: run._save_integrity(ckpts, y, run.sha256(release))


def test_live_rejects_unpinned_model_before_release(tmp_path, monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    cfg['model_revision']='main'
    with pytest.raises(RuntimeError,match='MODEL_REVISION_NOT_PINNED'):
        run.preflight(root,cfg,token,prepared,ckpt)
    assert calls==[]


def test_live_rejects_wrong_gpu_contract(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    cfg['model_dtype']='float16'
    # load_config reads saved correct values; mutate actual source for contract check
    f=root/'configs/lora.yaml'; f.write_text(yaml.safe_dump({'lora':cfg}),encoding='utf-8')
    with pytest.raises(RuntimeError,match='FP32'):
        run.load_config(f)


def test_live_preflight_requires_guard_for_every_stage(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    info=run.preflight(root,cfg,token,prepared,ckpt)
    assert calls==YEARS
    assert info['status']=='READY_FOR_RELEASED_EXECUTION'
    assert len(info['stages'])==5
    assert {x['status'] for x in info['stages']}=={'PENDING'}
    assert not ckpt.exists() and not results.exists()


def test_no_training_without_release(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    def denied(*args): raise RuntimeError('TRAINING_RELEASE_BLOCKED')
    monkeypatch.setattr(run,'require_training_release',denied)
    monkeypatch.setattr(run,'train_stage', lambda *a,**k:pytest.fail('training reached'))
    with pytest.raises(RuntimeError,match='TRAINING_RELEASE_BLOCKED'):
        run.execute(root,cfg,token,prepared,ckpt,results)
    assert not ckpt.exists() and not results.exists()


def test_reject_changed_prepared_year_file(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    (prepared/'train_2024.jsonl').write_text('tampered',encoding='utf-8')
    with pytest.raises(RuntimeError,match='STAGED_QA_HASH_INVALID'):
        run.preflight(root,cfg,token,prepared,ckpt)
    assert calls==[]


def test_existing_checkpoint_requires_release_and_sha(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    save_checkpoint(root,ckpt,2022,cfg,manifest,token)
    assert run.preflight(root,cfg,token,prepared,ckpt)['stages'][0]['status']=='VERIFIED_EXISTING'
    meta=ckpt/'year-2022/stage.json'; text=json.loads(meta.read_text())
    text['training_sha256']='tampered';meta.write_text(json.dumps(text))
    with pytest.raises(RuntimeError,match='CHECKPOINT_INTEGRITY_MISMATCH'):
        run.preflight(root,cfg,token,prepared,ckpt)


def test_reject_gap_in_checkpoint_chain(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    save_checkpoint(root,ckpt,2024,cfg,manifest,token)
    with pytest.raises(RuntimeError,match='CHECKPOINT_CHAIN_HAS_GAP'):
        run.preflight(root,cfg,token,prepared,ckpt)


def test_refuse_overwriting_results_before_training(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    results.mkdir()
    monkeypatch.setattr(run,'train_stage', lambda *a,**k:pytest.fail('training reached'))
    with pytest.raises(FileExistsError,match='REFUSE_TO_OVERWRITE_RESULTS'):
        run.execute(root,cfg,token,prepared,ckpt,results)


def test_full_five_stage_orchestration_and_evaluation(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    trained=[]; scored=[]
    def fake_training(config, prepared_dir, year, checkpoints, previous=None, **kwargs):
        if year > 2022: assert previous == checkpoints/f'year-{year-1}'
        assert kwargs['release_path']==token and kwargs['repo']==root
        trained.append(year)
        save_checkpoint(root,ckpt,year,cfg,manifest,token,integrity=False)
        return {'training_rows':1}
    def fake_eval(benchmark,years,predict,output):
        assert years==YEARS
        assert all((ckpt/f'year-{y}/stage.json').is_file() for y in YEARS)
        output.mkdir(parents=True)
        (output/'predictions.jsonl').write_text('testing outputs\n')
        scored.append(True)
        assert predict(2022,'What?',2022)=='synthetic'
        assert predict(2023,'What?',2022)=='synthetic'
        return {'unique_benchmark_cases':90, 'count':315}
    class FakeAnswerer:
        def __init__(self,config,path,allow_cpu):
            assert allow_cpu is False
        def answer(self,question,year):return {'answer':'synthetic','sources':[]}
    monkeypatch.setattr(run,'train_stage',fake_training)
    monkeypatch.setattr(run,'evaluate_stages',fake_eval)
    monkeypatch.setattr(run,'LoRAAnswerer',FakeAnswerer)
    monkeypatch.setattr(run,'_clear_gpu',lambda:None)
    report=run.execute(root,cfg,token,prepared,ckpt,results)
    assert trained==YEARS and scored==[True]
    assert report['evaluated_predictions']==315
    assert json.loads((results/'run_provenance.json').read_text())==report
    with pytest.raises(FileExistsError):
        run.execute(root,cfg,token,prepared,ckpt,results,resume=True)


def test_resume_keeps_completed_stage(tmp_path,monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    save_checkpoint(root,ckpt,2022,cfg,manifest,token)
    trained=[]
    def fake_training(config,prepared_dir,year,checkpoints,previous=None,**kw):
        trained.append(year)
        save_checkpoint(root,ckpt,year,cfg,manifest,token,integrity=False)
        return {'training_rows':1}
    monkeypatch.setattr(run,'train_stage',fake_training)
    monkeypatch.setattr(run,'_clear_gpu',lambda:None)
    monkeypatch.setattr(run,'evaluate_stages',lambda *a,**k: (results.mkdir(), {'unique_benchmark_cases':90,'count':315})[1])
    class FakeAnswerer:
        def __init__(self,*a,**k):pass
    monkeypatch.setattr(run,'LoRAAnswerer',FakeAnswerer)
    with pytest.raises(RuntimeError,match='CHECKPOINTS_ALREADY_EXIST'):
        run.execute(root,cfg,token,prepared,ckpt,results,resume=False)
    outcome=run.execute(root,cfg,token,prepared,ckpt,results,resume=True)
    assert trained==YEARS[1:]
    assert outcome['stages'][0]['status']=='REUSED_VERIFIED_CHECKPOINT'


def test_reject_modified_adapter_weights_even_with_valid_stage_metadata(tmp_path, monkeypatch):
    root,cfg,token,prepared,ckpt,results,calls,manifest=fixture(tmp_path,monkeypatch)
    save_checkpoint(root,ckpt,2022,cfg,manifest,token)
    (ckpt/'year-2022/adapter_model.safetensors').write_bytes(b'tampered adapter bytes')
    with pytest.raises(RuntimeError, match='CHECKPOINT_INTEGRITY_MISMATCH'):
        run.preflight(root,cfg,token,prepared,ckpt)
