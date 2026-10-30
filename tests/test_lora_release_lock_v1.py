"""Regression gates for live LoRA training release interlock (no ML deps)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.lora.contracts import sha256, write_jsonl
from src.lora.modeling import train_stage
from src.lora.release_guard import require_training_release


def _prepared(tmp_path: Path) -> Path:
    p = tmp_path / 'prepared'
    p.mkdir()
    f = p / 'train_2025.jsonl'
    write_jsonl(f, [{'id': 'example-2025', 'question': 'Q?', 'answer': 'A',
                     'doc_id': 'doc', 'as_of_year': 2025}])
    (p / 'manifest.json').write_text(json.dumps({
        'years': [2025], 'counts': {'2025': 1},
        'year_sha256': {'2025': sha256(f)}
    }), encoding='utf-8')
    return p


def test_live_training_blocks_before_model_import(tmp_path, monkeypatch):
    p = _prepared(tmp_path)
    import src.lora.modeling as mod
    monkeypatch.setattr(mod, '_libraries', lambda: pytest.fail('model must not load'))
    plan = train_stage({'base_model': 'test'}, p, 2025,
                       tmp_path / 'ckpt', dry_run=True)
    assert plan['dry_run'] is True and plan['model_loaded'] is False
    with pytest.raises(RuntimeError, match='TRAINING_RELEASE_BLOCKED'):
        train_stage({'base_model': 'test'}, p, 2025, tmp_path / 'ckpt')
    assert not (tmp_path / 'ckpt').exists()


def test_arbitrary_release_outside_repository_is_refused(tmp_path):
    p = _prepared(tmp_path)
    external = tmp_path / 'outside' / 'release.json'
    external.parent.mkdir()
    external.write_text('{}', encoding='utf-8')
    with pytest.raises(RuntimeError, match='TRAINING_RELEASE_BLOCKED'):
        require_training_release(p, p, 2025, external)


def test_forged_booleans_are_not_sufficient(tmp_path):
    p = _prepared(tmp_path)
    release = p / 'release.json'
    release.write_text(json.dumps({
        'schema': 'chronoreg-lora-release/v1',
        'status': 'owner_released',
        'independent_benchmark_review': True,
        'leakage_dispositions_reviewed': True,
        'owner_attestation': {
            'reviewer': 'dummy', 'reviewed_at': '2026-10-27',
            'decision_note': 'dummy attestation'
        }
    }), encoding='utf-8')
    with pytest.raises(RuntimeError, match='TRAINING_RELEASE_BLOCKED'):
        require_training_release(p, p, 2025, release)


def test_cli_has_release_option_without_importing_models():
    from src.lora.cli import main
    with pytest.raises(SystemExit) as exc:
        main(['train', '--help'])
    assert exc.value.code == 0
