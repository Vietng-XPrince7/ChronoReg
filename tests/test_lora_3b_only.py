"""Contract test: current ChronoReg LoRA tree has only the 3B model."""
from __future__ import annotations
import unittest
from pathlib import Path
from src.lora import qlora3b

ROOT = Path(__file__).resolve().parents[1]

class ThreeBOnlyContract(unittest.TestCase):
    def test_single_active_model_and_config(self):
        self.assertEqual(qlora3b.MODEL, 'Qwen/Qwen2.5-3B-Instruct')
        self.assertTrue((ROOT/'configs/lora.yaml').is_file())
        self.assertFalse((ROOT/'configs/lora_3b.yaml').exists())
        txt=(ROOT/'configs/lora.yaml').read_text(encoding='utf-8')
        self.assertIn(qlora3b.MODEL, txt)
        self.assertNotIn('Qwen2.5-' + '0' + '.5B',txt)

    def test_no_old_runtime(self):
        for path in ('src/lora/modeling.py', 'src/lora/release_guard.py',
                     'src/lora/run_five_stages.py', 'src/lora/smoke_stage.py',
                     'src/lora/adapter_smoke.py', 'scripts/run_demo_ubuntu.sh'):
            with self.subTest(path=path):
                self.assertFalse((ROOT/path).exists())

    def test_3b_cli_is_default(self):
        from src.lora import cli
        self.assertIs(cli.main, qlora3b.main)
        self.assertTrue(callable(qlora3b.run_answer))

    def test_shared_helpers_available(self):
        from src.lora.qa_runtime import messages, tokenize_qa, _verify_training_numerics
        from src.lora.benchmark_review import require_full_benchmark_review
        self.assertTrue(messages('Câu hỏi?', 2025))
        self.assertTrue(callable(tokenize_qa))
        self.assertTrue(callable(_verify_training_numerics))
        self.assertTrue(callable(require_full_benchmark_review))

    def test_release_gate_still_present(self):
        from src.lora import qlora3b_release
        self.assertTrue(callable(qlora3b_release.authorize))
        self.assertTrue(callable(qlora3b_release.require_full_benchmark_review))

if __name__ == '__main__':
    unittest.main()
