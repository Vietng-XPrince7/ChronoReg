"""Offline fail-closed regression for benchmark and training-configuration binding."""
from __future__ import annotations

import json
import pytest

from src.lora import run_five_stages as runner
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lora_five_stage_orchestration_v1 import fixture, save_checkpoint


def test_rejects_wrong_benchmark_before_model_call(tmp_path, monkeypatch):
    repo, cfg, release, prepared, checkpoints, output, calls, manifest = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, 'require_training_release',
                        lambda *args: {'release_file_sha256':runner.sha256(release),
                                      'benchmark_sha256': 'f' * 64})
    monkeypatch.setattr(runner, 'train_stage',
                        lambda *args, **kwargs:pytest.fail('Model training must not start'))
    with pytest.raises(RuntimeError, match='BENCHMARK_MISMATCH_BEFORE_TRAINING'):
        runner.execute(repo, cfg, release, prepared, checkpoints, output)
    assert not checkpoints.exists()


def test_custom_benchmark_path_is_checked(tmp_path, monkeypatch):
    repo, cfg, release, prepared, checkpoints, output, calls, manifest = fixture(tmp_path, monkeypatch)
    other = repo / 'data/qa_benchmark/frozen.jsonl'
    other.write_text('frozen snapshot\n', encoding='utf-8')
    cfg['benchmark'] = 'data/qa_benchmark/frozen.jsonl'
    monkeypatch.setattr(runner, 'require_training_release',
                        lambda *args: {'release_file_sha256':runner.sha256(release),
                                      'benchmark_sha256':runner.sha256(other)})
    plan = runner.preflight(repo, cfg, release, prepared, checkpoints)
    assert plan['benchmark_sha256'] == runner.sha256(other)
    assert plan['run_config_sha256'] == runner._run_config_sha256(cfg)


def test_rejects_outside_repository_benchmark(tmp_path, monkeypatch):
    repo, cfg, release, prepared, checkpoints, output, calls, manifest = fixture(tmp_path, monkeypatch)
    other = repo.parent / 'external.jsonl'
    other.write_text('foreign\n', encoding='utf-8')
    cfg['benchmark'] = '../external.jsonl'
    with pytest.raises(RuntimeError, match='BENCHMARK_PATH_INVALID'):
        runner.preflight(repo, cfg, release, prepared, checkpoints)


def test_config_change_refuses_existing_adapter(tmp_path, monkeypatch):
    repo, cfg, release, prepared, checkpoints, output, calls, manifest = fixture(tmp_path, monkeypatch)
    save_checkpoint(repo, checkpoints, 2022, cfg, manifest, release)
    assert runner.preflight(repo, cfg, release, prepared, checkpoints)['stages'][0]['status'] == 'VERIFIED_EXISTING'
    mutated = dict(cfg, learning_rate=0.2)
    with pytest.raises(RuntimeError, match='CHECKPOINT_INTEGRITY_MISMATCH'):
        runner.preflight(repo, mutated, release, prepared, checkpoints)


def test_unbound_v1_checkpoint_cannot_resume(tmp_path, monkeypatch):
    repo, cfg, release, prepared, checkpoints, output, calls, manifest = fixture(tmp_path, monkeypatch)
    save_checkpoint(repo, checkpoints, 2022, cfg, manifest, release)
    sidecar = checkpoints / 'year-2022/adapter_integrity.json'
    data = json.loads(sidecar.read_text(encoding='utf-8'))
    data['schema'] = 'chronoreg-adapter-integrity/v1'
    data.pop('run_config_sha256')
    sidecar.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(RuntimeError, match='CHECKPOINT_INTEGRITY_MISMATCH'):
        runner.preflight(repo, cfg, release, prepared, checkpoints)


def test_missing_release_still_blocks_training(tmp_path, monkeypatch):
    repo, cfg, release, prepared, checkpoints, output, calls, manifest = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, 'require_training_release',
                        lambda *args: (_ for _ in ()).throw(RuntimeError('TRAINING_RELEASE_BLOCKED')))
    monkeypatch.setattr(runner, 'train_stage',
                        lambda *args, **kwargs:pytest.fail('No model loading permitted'))
    with pytest.raises(RuntimeError, match='TRAINING_RELEASE_BLOCKED'):
        runner.execute(repo, cfg, release, prepared, checkpoints, output)
    assert not checkpoints.exists()
