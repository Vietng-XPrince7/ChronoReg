"""Fast/offline safety contracts. Real GPU smoke runs only on user hardware."""
import ast
from pathlib import Path

import pytest

from src.lora import smoke_stage


def test_synthetic_qa_is_fixed_and_explicit():
    a = smoke_stage.synthetic_qa(2025)
    b = smoke_stage.synthetic_qa(2026)
    assert a['id'] != b['id']
    assert a['question'] == b['question']
    assert 'không phải quy định UET' in a['answer']
    assert a['as_of_year'] == 2025 and b['as_of_year'] == 2026
    with pytest.raises(ValueError):
        smoke_stage.synthetic_qa(2024)


def test_smoke_does_not_import_or_call_production_train_stage():
    tree = ast.parse(Path(smoke_stage.__file__).read_text(encoding='utf-8'))
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert all('train_stage' not in ast.unparse(node) for node in imports)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert all(not (isinstance(n.func, ast.Name) and n.func.id in ('train_stage', 'require_training_release'))
               for n in calls)


def test_preflight_scoped_to_exact_model_and_no_training_release(tmp_path):
    f = tmp_path / 'configs' / 'lora.yaml'
    f.parent.mkdir(parents=True)
    f.write_text('lora:\n  base_model: Qwen/Qwen2.5-0.5B-Instruct\n'
                 '  strategy: sequential\n  model_dtype: float16\n', encoding='utf-8')
    result = smoke_stage.preflight(tmp_path)
    assert result['production_training_authorized'] is False
    assert result['uet_data_accessed'] is False
    assert result['model'] == 'Qwen/Qwen2.5-0.5B-Instruct'


def test_preflight_rejects_foreign_model(tmp_path):
    p = tmp_path / 'configs' / 'lora.yaml'
    p.parent.mkdir(parents=True)
    p.write_text('lora:\n  base_model: some-other-model\n  strategy: sequential\n'
                 '  model_dtype: float16\n', encoding='utf-8')
    with pytest.raises(ValueError, match='scoped'):
        smoke_stage.preflight(tmp_path)


def test_gpu_smoke_isolated_from_real_data_paths():
    code = Path(smoke_stage.__file__).read_text(encoding='utf-8')
    assert 'TemporaryDirectory' in code
    assert 'approved_qa.jsonl' not in code
    assert 'data/qa_benchmark' not in code
    assert 'data/raw/uet' not in code
    assert 'src/lora/runs' in code # documented explicitly as forbidden location
    assert 'train_stage(' not in code


def test_release_guard_is_still_called_by_real_trainer():
    from src.lora import modeling
    tree = ast.parse(Path(modeling.__file__).read_text(encoding='utf-8'))
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'train_stage')
    names = [n.id for n in ast.walk(func) if isinstance(n, ast.Name)]
    assert 'require_training_release' in names
