"""Offline tests for deterministic dtype selection and adapter checkpoint safety."""
from types import SimpleNamespace

import pytest

from src.lora.modeling import check_previous, model_loading_kwargs


class FakeCuda:
    def __init__(self, bf16=False):
        self.bf16 = bf16

    def is_bf16_supported(self):
        return self.bf16


def fake_torch(bf16=False):
    return SimpleNamespace(float16='f16', float32='f32', bfloat16='bf16',
                           cuda=FakeCuda(bf16))


def test_t1000_default_is_explicit_fp16():
    opts = model_loading_kwargs({}, fake_torch(), on_cuda=True)
    assert opts['dtype'] == 'f16'
    assert opts['attn_implementation'] == 'eager'
    assert opts['trust_remote_code'] is False
    assert opts['use_safetensors'] is True


def test_cpu_smoke_forces_fp32():
    assert model_loading_kwargs({}, fake_torch(), on_cuda=False)['dtype'] == 'f32'


def test_turing_rejects_bf16():
    with pytest.raises(ValueError, match='without BF16 support'):
        model_loading_kwargs({'model_dtype': 'bfloat16'}, fake_torch(), on_cuda=True)
    assert model_loading_kwargs({'model_dtype': 'bfloat16'}, fake_torch(bf16=True), on_cuda=True)['dtype'] == 'bf16'


def test_invalid_dtype_fails_closed():
    with pytest.raises(ValueError, match='Unsupported model_dtype'):
        model_loading_kwargs({'model_dtype': 'auto'}, fake_torch(), on_cuda=True)


def test_previous_checkpoint_requires_nonempty_weights(tmp_path):
    previous = tmp_path / 'year-2025'
    previous.mkdir()
    (previous / 'adapter_config.json').write_text('{}', encoding='utf-8')
    (previous / 'stage.json').write_text('{"year":2025,"model":"base","model_revision":"main","strategy":"sequential","model_dtype":"float16"}', encoding='utf-8')
    with pytest.raises(ValueError, match='Missing complete'):
        check_previous(previous, 2026, {'base_model':'base'})
    weights = previous / 'adapter_model.safetensors'
    weights.touch()
    with pytest.raises(ValueError, match='Missing complete'):
        check_previous(previous, 2026, {'base_model':'base'})
    weights.write_bytes(b'synthetic-fixture')
    assert check_previous(previous, 2026, {'base_model':'base'})['year'] == 2025
    with pytest.raises(ValueError, match='dtype changed'):
        check_previous(previous, 2026, {'base_model':'base','model_dtype':'float32'})
