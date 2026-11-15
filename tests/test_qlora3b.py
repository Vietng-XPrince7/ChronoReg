"""Offline tests for QLoRA3B pipeline. No GPU, model downloads, real releases."""
from __future__ import annotations

import hashlib
import csv
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.lora import qlora3b as q


class QLoRA3BOfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.config = {
            'base_model': q.MODEL, 'model_revision': q.PIN,
            'strategy': 'sequential', 'model_dtype': 'float16',
            'quantization': q.QUANT, 'years': q.YEARS, 'max_seq_length': 512,
            'minimum_gpu_gib': 12, 'minimum_total_qa': 200,
            'minimum_qa_per_year': 30, 'learning_rate': 0.0001,
            'epochs': 2, 'train_batch_size': 1,
            'gradient_accumulation_steps': 8, 'lora_r': 8,
            'lora_alpha': 16, 'lora_dropout': 0.05, 'seed': 42,
            'max_new_tokens': 160,
            'target_modules': ['q_proj','k_proj','v_proj','o_proj'],
            'benchmark': 'data/qa_benchmark/benchmark.jsonl'
        }

    def fixtures(self):
        src = self.repo / 'data/raw/uet/markdown/2025/source.md'
        src.parent.mkdir(parents=True)
        evidence = 'Quy định kiểm thử giả lập; không liên quan đến UET thật.'
        src.write_text(evidence, encoding='utf-8')
        sh = hashlib.sha256(src.read_bytes()).hexdigest()
        qa = []
        for year in q.YEARS:
            for n in range(40):
                qa.append({'id': f'fixture-{year}-{n:03}',
                           'question': f'Câu hỏi kiểm thử giả lập {year} số {n}?',
                           'answer': f'Đáp án thử {year}-{n}',
                           'doc_id': 'fake-source', 'as_of_year': year,
                           'academic_year': f'{year}-{year + 1}',
                           'evidence_quote': evidence,
                           'source_file': 'data/raw/uet/markdown/2025/source.md',
                           'source_sha256': sh, 'review_status': 'approved'})
        bench = [{'id': f'heldout-{n}', 'question': f'Benchmark khác biệt {n}?',
                  'gold_answer': f'gold-{n}', 'gold_doc_id': 'heldout',
                  'as_of_year': 2022 + n % 5, 'type': 'temporal_specific'}
                 for n in range(90)]
        train_path = self.repo / 'data/qa/fixture.jsonl'
        benchmark_path = self.repo / self.config['benchmark']
        train_path.parent.mkdir(parents=True)
        benchmark_path.parent.mkdir(parents=True)
        for p, rows in ((train_path, qa), (benchmark_path, bench)):
            p.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows),
                         encoding='utf-8')
        return train_path, benchmark_path, qa, bench

    def test_stage_200_fake_rows_only_as_test_fixture(self):
        self.fixtures()
        folder = self.repo / 'staged'
        result = q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                                 self.config['benchmark'], folder)
        self.assertEqual(result['status'], 'STAGED_NOT_RELEASED')
        self.assertEqual(result['rows'], 200)
        self.assertEqual(result['counts'], {str(y): 40 for y in q.YEARS})
        with self.assertRaises(FileExistsError):
            q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                            self.config['benchmark'], folder)

    def test_benchmark_leakage_refused(self):
        train_path, _, rows, benchmark = self.fixtures()
        benchmark[0]['question'] = rows[0]['question']
        (self.repo / self.config['benchmark']).write_text(
            ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in benchmark),
            encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'overlaps held-out benchmark'):
            q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                            self.config['benchmark'], self.repo / 'staged')

    def test_legacy_template_ids_refused(self):
        train_path, _, rows, _ = self.fixtures()
        rows[0]['id'] = 'train-2022-001'
        train_path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n'
                                      for x in rows), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'legacy'):
            q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                            self.config['benchmark'], self.repo / 'staged')

    def test_underfilled_stage_refused(self):
        train_path, _, rows, _ = self.fixtures()
        rows = [row for row in rows if row['as_of_year'] != 2026 or row['id'].endswith('000')]
        train_path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n'
                                      for x in rows), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'not enough'):
            q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                            self.config['benchmark'], self.repo / 'staged')

    def test_release_without_owner_dossier_fails_closed(self):
        self.fixtures()
        prepared = self.repo / 'staged'
        q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                        self.config['benchmark'], prepared)
        with self.assertRaisesRegex(RuntimeError, 'owner release'):
            q.preflight(self.repo, self.config, prepared, None, self.repo / 'checkpoints')
        self.assertFalse((self.repo / 'checkpoints').exists())

    def test_bad_release_status_blocked(self):
        self.fixtures()
        prepared = self.repo / 'staged'
        q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                        self.config['benchmark'], prepared)
        release = self.repo / 'release.json'
        release.write_text(json.dumps({'schema': 'chronoreg-qlora3b-release/v1',
                                       'status': 'draft'}), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'independent QA'):
            q.preflight(self.repo, self.config, prepared, release, self.repo / 'checkpoints')

    def test_gpu_4_gib_rejected_before_model_loading(self):
        fake = types.ModuleType('torch')
        fake.cuda = types.SimpleNamespace(
            is_available=lambda: True,
            get_device_properties=lambda i: types.SimpleNamespace(
                name='Quadro T1000', total_memory=4 * 1024 ** 3))
        with patch.dict(sys.modules, {'torch': fake}):
            with self.assertRaisesRegex(RuntimeError, '4GB T1000'):
                q.gpu_preflight(self.config)

    def test_pin_and_dtype_rejected_if_changed(self):
        fake_yaml = types.ModuleType('yaml')
        fake_yaml.safe_load = lambda _: {'lora': dict(self.config, model_revision='main')}
        source = self.repo / 'profile.yaml'
        source.write_text('fixture\n')
        with patch.dict(sys.modules, {'yaml': fake_yaml}):
            with self.assertRaisesRegex(RuntimeError, '3B_CONFIG_INVALID'):
                q.load_cfg(source)

    def test_checkpoint_tamper_and_5_year_chain(self):
        auth = {'release_sha256': 'f' * 64}
        manifest = {'year_sha256': {str(y): str(y) * 16 for y in q.YEARS}}
        checkpoints = self.repo / 'checkpoints'
        for year in q.YEARS:
            folder = checkpoints / f'year-{year}'
            folder.mkdir(parents=True)
            (folder / 'adapter_model.safetensors').write_bytes(b'fictional weights fixture')
            (folder / 'adapter_config.json').write_text('{}')
            meta = {'year': year, 'model': q.MODEL, 'model_revision': q.PIN,
                    'model_dtype': 'float16', 'quantization': q.QUANT,
                    'strategy': 'sequential',
                    'training_sha256': manifest['year_sha256'][str(year)],
                    'release_sha256': auth['release_sha256'],
                    'previous_year': year - 1 if year > 2022 else None}
            (folder / 'stage.json').write_text(json.dumps(meta))
            files = ['adapter_model.safetensors', 'adapter_config.json', 'stage.json']
            sidecar = {'schema': 'chronoreg-qlora3b-integrity/v1', 'year': year,
                       'run_config_sha256': q.cfg_hash(self.config),
                       'release_file_sha256': auth['release_sha256'],
                       'file_sha256': {name: q.sha256(folder / name) for name in files}}
            (folder / 'adapter_integrity.json').write_text(json.dumps(sidecar))
        self.assertEqual(q.checkpoint_chain(checkpoints, self.config, auth, manifest), q.YEARS)
        (checkpoints / 'year-2024/adapter_model.safetensors').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'INTEGRITY_MISMATCH'):
            q.checkpoint_chain(checkpoints, self.config, auth, manifest)

    def test_synthetic_release_ledger_binding_and_tamper(self):
        # Test-only artificial attestations. NEVER a real training authorization.
        train_file, benchmark_file, rows, bench = self.fixtures()
        prepared = self.repo / 'staged'
        q.stage_dataset(self.repo, self.config, 'data/qa/fixture.jsonl',
                        self.config['benchmark'], prepared)
        evidence_dir = self.repo / 'test-evidence'
        evidence_dir.mkdir()
        def csv_file(name, rows):
            out = evidence_dir / name
            with out.open('w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            return out
        def h(t): return hashlib.sha256(t.encode('utf-8')).hexdigest()
        ledger = csv_file('qa.csv', [
            dict(candidate_id=row['id'], decision='approve',
                 source_verified='YES', cohort_effectivity_verified='YES',
                 semantic_leakage_cleared='YES', independent_reviewer_signoff='YES',
                 reviewer='fixture-only', reviewed_at='fixture-only',
                 reviewer_note='synthetic fixture, not a review',
                 question_sha256=h(row['question']), answer_sha256=h(row['answer']),
                 source_sha256=row['source_sha256']) for row in rows
        ])
        corrections = csv_file('corrections.csv', [
            dict(benchmark_id=f'heldout-{i}',owner_accepted='YES',final_freeze_eligible='YES')
            for i in range(42)])
        overlaps = [
            dict(candidate_id=f'old-{i}', benchmark_id=f'heldout-{i}',
                 training_payload_evidence_checked='YES',
                 independent_reviewer_signoff='YES',fact_level_disposition='CLEARED')
            for i in range(59)]
        leak = csv_file('leakage.csv', overlaps)
        inventory = csv_file('inventory.csv', [
            dict(candidate_id=x['candidate_id'], benchmark_id=x['benchmark_id'])
            for x in overlaps])
        benchmark_review = csv_file('benchmark_review.csv', [
            dict(benchmark_id=x['id'], gold_answer_sha256=h(x['gold_answer']))
            for x in bench])
        freeze_manifest = evidence_dir / 'freeze.json'
        freeze_manifest.write_text(json.dumps({'fixture_only': True}), encoding='utf8')
        release_path = self.repo / 'release_fixture.json'
        review_spec = {
            'qa_review_ledger': ledger,
            'benchmark_evidence_ledger': corrections,
            'leakage_disposition_ledger': leak,
            'overlap_inventory_file': inventory,
            'full_benchmark_review_ledger': benchmark_review,
            'benchmark_freeze_manifest': freeze_manifest,
            'curated_train_file': train_file,
            'benchmark_file': benchmark_file,
        }
        release = dict(schema='chronoreg-qlora3b-release/v1',
                       status='owner_released', independent_training_review=True,
                       independent_benchmark_review=True,
                       semantic_leakage_reviewed=True,
                       owner_attestation={'reviewer':'test fixture',
                                          'reviewed_at':'test fixture',
                                          'decision_note':'not a real signoff'},
                       prepared_manifest_sha256=q.sha256(prepared/'manifest.json'))
        sha_names = {'qa_review_ledger':'qa_review_sha256',
                     'benchmark_evidence_ledger':'benchmark_evidence_sha256',
                     'leakage_disposition_ledger':'leakage_disposition_sha256',
                     'overlap_inventory_file':'overlap_inventory_sha256',
                     'full_benchmark_review_ledger':'full_benchmark_review_sha256',
                     'benchmark_freeze_manifest':'benchmark_freeze_manifest_sha256',
                     'curated_train_file':'curated_train_sha256',
                     'benchmark_file':'benchmark_sha256'}
        for key, path in review_spec.items():
            release[key] = str(path.relative_to(self.repo)).replace('\\','/')
            release[sha_names[key]] = q.sha256(path)
        release_path.write_text(json.dumps(release), encoding='utf8')
        from src.lora import qlora3b_release as gate
        # The main repo tests cover its real benchmark review validator.
        with patch.object(gate, 'require_full_benchmark_review', return_value=None):
            _, result = q.preflight(self.repo, self.config, prepared,
                                    release_path, self.repo/'checkpoints')
            self.assertEqual(result['status'], 'READY_FOR_GPU_PREFLIGHT')
            self.assertEqual(result['training_rows'], 200)
            ledger.write_text(ledger.read_text(encoding='utf8') + 'tamper',encoding='utf8')
            with self.assertRaisesRegex(RuntimeError, 'changed source/ledger'):
                q.preflight(self.repo, self.config, prepared,
                            release_path, self.repo/'checkpoints')

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'outside repository'):
            q.relative_file(self.repo, '../otherrepo/secret.jsonl')

    def test_base_model_hash_stable(self):
        self.assertEqual(q.cfg_hash(self.config), q.cfg_hash(dict(reversed(list(self.config.items())))))


if __name__ == '__main__':
    unittest.main()
