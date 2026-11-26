import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from src.lora.web_runtime import WebLoRARuntime
from src.lora import verified_v3
from src.api import studenthub_server as server, academic_dispatch


class FakeV3:
    def __init__(self):
        self._model = self._tok = None
        self.loads = 0
        self.calls = 0
    def _load(self):
        self.loads += 1
        self._model = self._tok = object()
        self._device = 'fake_gpu'
    def generate(self, question, *, as_of_year=None):
        self.calls += 1
        return {'answer': 'Fake test output, not actual GPU inference', 'engine_mode': 'LIVE_PEFT_GENERATION',
                'checkpoint_year': 2026, 'latency_ms': 1}


def install_runtime(monkeypatch, factory):
    runtime = WebLoRARuntime()
    monkeypatch.setattr(verified_v3, 'from_environment', factory)
    monkeypatch.setattr(server, 'web_lora', runtime)
    monkeypatch.setattr(academic_dispatch, 'web_lora', runtime)
    return runtime


def test_startup_loads_once_and_all_three_endpoints_share_model(monkeypatch):
    model = FakeV3()
    runtime = install_runtime(monkeypatch, lambda: model)
    with TestClient(server.app) as client:
        assert model.loads == 1 and model.calls == 0
        assert client.get('/api/lora/status').json()['ready'] is True
        client.get('/'); client.get('/')
        q = 'Học phí năm 2026 là bao nhiêu?'
        r = client.post('/api/chat', json={'question': q, 'force_engine': 'continual_lora'}).json()
        assert r['metadata']['engine_mode'] == 'LIVE_PEFT_GENERATION'
        assert r['metadata']['quality_qualified'] is False
        r = client.post('/api/compare', json={'question': q}).json()
        assert r['continual_lora']['metadata']['engine_mode'] == 'LIVE_PEFT_GENERATION'
        r = client.post('/api/answer-v2', json={'question': q, 'compare': True}).json()
        assert r['comparison']['lora']['engine_mode'] == 'LIVE_PEFT_GENERATION'
        assert not r['authoritative_regulation_answer']
        runtime.preload()
        assert model.loads == 1 and model.calls == 3


def test_missing_model_is_explicit_and_does_not_stop_web(monkeypatch):
    attempts = []
    def fail():
        attempts.append(1)
        raise RuntimeError('V3 adapter missing')
    install_runtime(monkeypatch, fail)
    with TestClient(server.app) as client:
        assert client.get('/').status_code == 200
        status = client.get('/api/lora/status').json()
        assert not status['ready'] and status['status'] == 'UNAVAILABLE'
        q = 'Học phí năm 2026 là bao nhiêu?'
        r = client.post('/api/chat', json={'question': q, 'force_engine': 'continual_lora'}).json()
        assert r['metadata']['engine_mode'] in ('LORA_UNAVAILABLE', 'CACHED_FALLBACK', 'OLLAMA_LOCAL', 'REMOTE_GPU')
        assert r['metadata']['quality_qualified'] is False
        assert 'inference_source' in r['metadata']
        r = client.post('/api/compare', json={'question': q}).json()
        assert r['continual_lora']['metadata']['engine_mode'] in ('LORA_UNAVAILABLE', 'CACHED_FALLBACK', 'OLLAMA_LOCAL', 'REMOTE_GPU')
        assert len(attempts) == 1
        r = client.post('/api/chat', json={'question': 'Xin cứu xét ngoại lệ miễn học phí', 'force_engine': 'continual_lora'}).json()
        assert r['routing']['actual_engine_used'] == 'safety_gate_red'


def test_non_live_response_rejected(monkeypatch):
    model = FakeV3()
    model.generate = lambda *a, **kw: {'answer':'stored', 'engine_mode':'VERIFIED_BENCHMARK_PREDICTION'}
    install_runtime(monkeypatch, lambda: model)
    with TestClient(server.app) as client:
        r = client.post('/api/chat', json={'question':'Học phí năm 2026?', 'force_engine':'continual_lora'}).json()
        assert r['metadata']['engine_mode'] == 'LORA_UNAVAILABLE'
        assert 'stored' not in r['answer']
