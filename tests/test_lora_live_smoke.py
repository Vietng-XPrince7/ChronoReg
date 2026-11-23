"""CPU-only regressions for the genuine PEFT smoke and pinned Transformers compatibility."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lora_live_smoke import file_preflight, run_live
from src.lora.verified_v3 import VerifiedV3Inference


def test_preflight_fails_closed_without_models(tmp_path):
    with pytest.raises(Exception):
        file_preflight(tmp_path)


def test_live_fails_closed_before_gpu_if_missing_models(tmp_path):
    with pytest.raises(Exception):
        run_live(tmp_path, "Học phí?", 2026, None)


def test_no_answer_replay_or_implicit_download(tmp_path):
    script = ROOT / "scripts/lora_live_smoke.py"
    cmd = [sys.executable, str(script), "--preflight", "--models-root", str(tmp_path)]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    assert cp.returncode != 0
    report = json.loads(cp.stdout)
    assert report["status"] == "FAILED"
    assert not report["live_inference_tested"]
    assert not report["quality_qualified"]
    assert not list(tmp_path.iterdir())


def test_transformers_4_46_uses_torch_dtype_not_dtype(tmp_path, monkeypatch):
    seen = {}
    class FakeTokenizer:
        pad_token_id = 0
        def from_pretrained(self, *args, **kwargs):
            return self
    class FakeModel:
        def from_pretrained(self, *args, **kwargs):
            seen.update(kwargs)
            return self
    class FakePeft:
        def from_pretrained(self, base, *args, **kwargs):
            return self
        def eval(self):
            return self
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False,
        device_count=lambda: 0), float32="FP32", float16="FP16")
    fake_transformers = SimpleNamespace(
        AutoModelForCausalLM=FakeModel(), AutoTokenizer=FakeTokenizer(),
        BitsAndBytesConfig=lambda **kw: kw)
    fake_peft = SimpleNamespace(PeftModel=FakePeft())
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)
    instance = object.__new__(VerifiedV3Inference)
    instance.root = tmp_path
    instance.base = tmp_path
    instance.year = 2026
    instance.allow_cpu = True
    instance._model = None
    instance._tok = None
    instance._load()
    assert seen["torch_dtype"] == "FP32"
    assert "dtype" not in seen
    assert seen["trust_remote_code"] is False
    assert seen["local_files_only"] is True
    assert instance._model is not None
