"""CPU-only regression checks for the approved-data LoRA numerical safety gate."""
from pathlib import Path
import pytest
import yaml

from src.lora import modeling, smoke_stage


def test_production_config_matches_measured_gpu_shape():
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / 'configs/lora.yaml').read_text(encoding='utf-8'))['lora']
    assert cfg['model_dtype'] == 'float32'
    assert cfg['base_model'] == 'Qwen/Qwen2.5-0.5B-Instruct'
    assert cfg['years'] == [2022, 2023, 2024, 2025, 2026]
    assert cfg['max_seq_length'] == 512
    assert cfg['train_batch_size'] == 1
    assert cfg['gradient_accumulation_steps'] == 8
    assert cfg['epochs'] == 2
    assert smoke_stage._read_config(root)['model_dtype'] == 'float32'


def test_numeric_validation_detects_real_update():
    torch = pytest.importorskip('torch')
    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_B = torch.nn.Parameter(torch.zeros(3))
            self.other = torch.nn.Parameter(torch.ones(3), requires_grad=False)
    toy = Toy()
    before = modeling._training_adapter_snapshot(toy, torch)
    logs = [{'grad_norm': 1.2, 'loss': 0.9}]
    with pytest.raises(RuntimeError, match='no adapter update'):
        modeling._verify_training_numerics(toy, torch, before, logs, 0.9, 1)
    with torch.no_grad():
        toy.lora_B[0].add_(0.005)
    result = modeling._verify_training_numerics(toy, torch, before, logs, 0.9, 1)
    assert result['optimizer_steps'] == 1
    assert result['max_abs_adapter_update'] > 0
    assert result['updated_adapter_tensors'] == 1


@pytest.mark.parametrize('logs,loss,steps', [
    ([{'grad_norm': float('nan'), 'loss': 2.0}], 2.0, 1),
    ([{'grad_norm': 0.0, 'loss': 2.0}], 2.0, 1),
    ([{'grad_norm': float('inf'), 'loss': 2.0}], 2.0, 1),
    ([{'grad_norm': 1.0, 'loss': float('nan')}], 2.0, 1),
    ([{'loss': 2.0}], 2.0, 1),
    ([{'grad_norm': 1.0, 'loss': 2.0}], float('nan'), 1),
    ([{'grad_norm': 1.0, 'loss': 2.0}], 2.0, 0),
])
def test_numeric_validation_fails_closed(logs, loss, steps):
    torch = pytest.importorskip('torch')
    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_B = torch.nn.Parameter(torch.ones(3))
    toy = Toy()
    before = modeling._training_adapter_snapshot(toy, torch)
    with torch.no_grad():
        toy.lora_B[0].add_(0.5)
    with pytest.raises(RuntimeError, match='TRAINING_NUMERIC_BLOCKED'):
        modeling._verify_training_numerics(toy, torch, before, logs, loss, steps)


def test_nonfinite_weights_rejected():
    torch = pytest.importorskip('torch')
    class Toy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_A = torch.nn.Parameter(torch.ones(2))
    toy = Toy()
    before = modeling._training_adapter_snapshot(toy, torch)
    with torch.no_grad():
        toy.lora_A[0] = float('nan')
    with pytest.raises(RuntimeError, match='nonfinite adapter'):
        modeling._verify_training_numerics(toy, torch, before,
                                            [{'grad_norm': 1.0, 'loss': 1.0}],1.0,1)


def test_training_release_still_required():
    import ast
    tree = ast.parse(Path(modeling.__file__).read_text(encoding='utf-8'))
    train = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'train_stage')
    import_names = {x.id for x in ast.walk(train) if isinstance(x, ast.Name)}
    assert 'require_training_release' in import_names
    code = Path(modeling.__file__).read_text(encoding='utf-8')
    assert code.index('require_training_release(repo, prepared_dir, year, release_path)') < code.index('starting_adapters = _training_adapter_snapshot(model, torch)')
    assert "logging_steps=1, remove_unused_columns=False" in code
