"""Eight GPU-free tests; stdlib unittest, also collected by pytest."""
import json
import tempfile
import unittest
from pathlib import Path

from src.lora.adapter_smoke import check_checkpoint, check_chain, AdapterCheckError

CFG = {
    'base_model': 'Qwen/Qwen2.5-0.5B-Instruct',
    'model_revision': '7ae557604adf67be50417f59c2c2f167def9a775',
    'strategy': 'sequential', 'model_dtype': 'float32',
    'years': [2022, 2023, 2024, 2025, 2026], 'lora_r': 8, 'lora_alpha': 16,
}


def stage(root, year, *, model=None):
    directory = root / f'year-{year}'
    directory.mkdir(parents=True)
    (directory / 'adapter_model.safetensors').write_bytes(b'not-a-real-model:unit-tests-only')
    (directory / 'adapter_config.json').write_text(json.dumps({
        'base_model_name_or_path': model or CFG['base_model'],
        'peft_type': 'LORA', 'task_type': 'CAUSAL_LM', 'r': 8, 'lora_alpha': 16,
    }), encoding='utf-8')
    (directory / 'stage.json').write_text(json.dumps({
        'year': year, 'model': CFG['base_model'], 'model_revision': CFG['model_revision'],
        'model_dtype': 'float32', 'strategy': 'sequential', 'training_rows': 5,
    }), encoding='utf-8')
    return directory


class TestAdapterSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_valid_5_year_chain_is_demo_only(self):
        for year in range(2022, 2027):
            stage(self.root, year)
        result = check_chain(self.root, CFG)
        self.assertEqual(result['check'], 'PASS_STRUCTURAL_ONLY')
        self.assertEqual(result['status'], 'DEMO_UNRELEASED')
        self.assertEqual(result['adapter_count'], 5)
        self.assertEqual(result['training_rows_from_stage_metadata'], 25)
        self.assertFalse(any(x['released_for_training_or_student_qa']
                             for x in result['checkpoints']))

    def test_bad_model_refused(self):
        directory = stage(self.root, 2026, model='other/base')
        with self.assertRaisesRegex(AdapterCheckError, 'PEFT metadata incompatible'):
            check_checkpoint(directory, 2026, CFG)

    def test_wrong_revision_refused(self):
        directory = stage(self.root, 2026)
        path = directory / 'stage.json'
        meta = json.loads(path.read_text())
        meta['model_revision'] = 'main'
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(AdapterCheckError, 'Stage metadata mismatch'):
            check_checkpoint(directory, 2026, CFG)

    def test_missing_weights_refused(self):
        directory = stage(self.root, 2026)
        (directory / 'adapter_model.safetensors').unlink()
        with self.assertRaisesRegex(AdapterCheckError, 'Missing/empty/unsafe'):
            check_checkpoint(directory, 2026, CFG)

    def test_wrong_year_refused(self):
        directory = stage(self.root, 2025)
        with self.assertRaisesRegex(AdapterCheckError, 'Stage metadata mismatch'):
            check_checkpoint(directory, 2026, CFG)

    def test_non_positive_training_rows_refused(self):
        directory = stage(self.root, 2026)
        path = directory / 'stage.json'
        meta = json.loads(path.read_text())
        meta['training_rows'] = 0
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(AdapterCheckError, 'training_rows'):
            check_checkpoint(directory, 2026, CFG)

    def test_sidecar_tampering_refused(self):
        directory = stage(self.root, 2026)
        (directory / 'adapter_integrity.json').write_text(json.dumps({
            'schema': 'chronoreg-adapter-integrity/v2', 'year': 2026,
            'file_sha256': {k: '0' * 64 for k in
                            ['adapter_model.safetensors','adapter_config.json','stage.json']},
        }), encoding='utf-8')
        with self.assertRaisesRegex(AdapterCheckError, 'sidecar hash mismatch'):
            check_checkpoint(directory, 2026, CFG)

    def test_bad_rank_refused(self):
        directory = stage(self.root, 2026)
        path = directory / 'adapter_config.json'
        data = json.loads(path.read_text())
        data['r'] = 16
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(AdapterCheckError, 'PEFT r incompatible'):
            check_checkpoint(directory, 2026, CFG)


if __name__ == '__main__':
    unittest.main()
