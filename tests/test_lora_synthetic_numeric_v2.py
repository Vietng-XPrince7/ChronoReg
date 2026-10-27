"""Offline numerical proof checks for isolated synthetic LoRA GPU smoke."""
from __future__ import annotations

import importlib.util
import math
import unittest
from pathlib import Path

import pytest

from src.lora import smoke_stage


def test_nonfinite_gradient_rejected():
    with pytest.raises(RuntimeError, match='NONFINITE_GRADIENT'):
        smoke_stage._finite_training_logs([{'grad_norm': float('nan'), 'loss': 2.9}])
    with pytest.raises(RuntimeError, match='NONFINITE_GRADIENT'):
        smoke_stage._finite_training_logs([{'grad_norm': float('inf'), 'loss': 2.9}])
    with pytest.raises(RuntimeError, match='NONFINITE_GRADIENT'):
        smoke_stage._finite_training_logs([{'grad_norm': 0.0, 'loss': 2.9}])


def test_missing_optimizer_step_rejected():
    with pytest.raises(RuntimeError, match='NO_EFFECTIVE_OPTIMIZER_STEP'):
        smoke_stage._finite_training_logs([{'loss': 2.9}])


def test_nonfinite_loss_rejected():
    with pytest.raises(RuntimeError, match='NONFINITE_TRAINING_LOSS'):
        smoke_stage._finite_training_logs([{'grad_norm': 0.3, 'loss': float('nan')}])


def test_finite_step_accepted():
    result = smoke_stage._finite_training_logs([{'grad_norm': 0.3, 'loss': 2.9}, {'train_loss': 2.9}])
    assert result == {'grad_norm': 0.3, 'loss': 2.9}


def test_weight_change_required():
    torch = pytest.importorskip('torch')
    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_B = torch.nn.Parameter(torch.ones(3))
            self.frozen = torch.nn.Parameter(torch.ones(3), requires_grad=False)
    model = Toy()
    before = smoke_stage._trainable_adapter_snapshot(model, torch)
    with pytest.raises(RuntimeError, match='ZERO_ADAPTER_UPDATE'):
        smoke_stage._verified_parameter_update(before, model, torch)
    with torch.no_grad():
        model.lora_B.add_(0.125)
    result = smoke_stage._verified_parameter_update(before, model, torch)
    assert result['updated_tensors'] == 1
    assert result['max_abs_delta'] > 0
    with torch.no_grad():
        model.lora_B[0] = float('nan')
    with pytest.raises(RuntimeError, match='NONFINITE_ADAPTER_AFTER_TRAINING'):
        smoke_stage._verified_parameter_update(before, model, torch)


def test_smoke_uses_fp32_and_no_live_training():
    text = Path(smoke_stage.__file__).read_text(encoding='utf-8')
    assert "cfg = dict(_read_config(repo), model_dtype='float32')" in text
    assert 'bf16=False, fp16=False' in text
    assert 'train_stage(' not in text
    assert '_finite_training_logs(trainer.state.log_history)' in text
    assert '_verified_parameter_update(initial_adapters, model, torch)' in text
    assert 'temporary_artifacts_removed_on_exit' in text
