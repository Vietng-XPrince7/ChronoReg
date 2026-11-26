"""Unit tests for ChronoRegLLMBackend (3-tier Ollama / Remote GPU / Cached Fallback) and /api/health."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.llm_backend import ChronoRegLLMBackend
from src.rag.eval_adapter import InMemoryRetriever, RAGEvalAdapter


@pytest.fixture(scope="module")
def shared_rag():
    retriever = InMemoryRetriever.from_corpus()
    adapter = RAGEvalAdapter(retriever)
    return retriever, adapter


def _mock_ollama_client(
    *,
    models: list[str] | None = None,
    ollama_up: bool = True,
    remote_up: bool = False,
    captured_requests: list[dict] | None = None,
) -> httpx.Client:
    """Create an httpx.Client backed by MockTransport for deterministic tests."""
    avail = models if models is not None else ["chronoreg-base:3b", "chronoreg-lora:3b"]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = None
        if request.content:
            try:
                body = json.loads(request.content.decode("utf-8"))
            except Exception:
                body = request.content.decode("utf-8", errors="replace")

        if captured_requests is not None:
            captured_requests.append({"method": request.method, "url": url, "body": body})

        # Tier 1: Local Ollama endpoints
        if "localhost:11434" in url or "127.0.0.1:11434" in url:
            if not ollama_up:
                raise httpx.ConnectError("Connection refused (mock Ollama off)", request=request)
            if url.endswith("/api/tags"):
                return httpx.Response(200, json={"models": [{"name": m} for m in avail]})
            if url.endswith("/api/chat"):
                model_used = (body or {}).get("model", "")
                if model_used.startswith("chronoreg-lora"):
                    return httpx.Response(
                        200,
                        json={
                            "message": {
                                "role": "assistant",
                                "content": "Theo quy định đào tạo UET, sinh viên nộp đơn bảo lưu tại Phòng Đào tạo trước học kỳ.",
                            }
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "message": {
                            "role": "assistant",
                            "content": "Theo QĐ 2377/QĐ-ĐHCN năm học 2026-2027, mức học phí tín chỉ CTĐT chuẩn khóa QH-2021 trở về trước là 570.000 đồng/tín chỉ.",
                        }
                    },
                )

        # Tier 2: Remote GPU tunnel endpoint
        if "remote-gpu.example" in url:
            if not remote_up:
                raise httpx.ConnectError("Remote tunnel unreachable", request=request)
            return httpx.Response(
                200,
                json={"answer": "Phản hồi từ Remote GPU Tunnel (Qwen2.5-3B)."},
            )

        return httpx.Response(404, json={"error": "Not found"})

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestOllamaHealthCheck:
    def test_health_ready_when_both_models_installed(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=True)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        health = backend.check_ollama_health()
        assert health["ollama_reachable"] is True
        assert health["base_model_ready"] is True
        assert health["lora_model_ready"] is True
        assert health["ready"] is True
        assert health["all_models_ready"] is True
        assert health["inference_source"] == "ollama_local"
        assert health["engine_label"] == "Engine: Ollama 3B Local (Ready)"

    def test_health_fallback_when_ollama_unreachable(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=False)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        health = backend.check_ollama_health()
        assert health["ollama_reachable"] is False
        assert health["base_model_ready"] is False
        assert health["lora_model_ready"] is False
        assert health["ready"] is False
        assert health["inference_source"] == "cached_fallback"
        assert health["engine_label"] == "Engine: Cached / Extractive Mode"


class TestThreeTierInference:
    def test_tier1_ollama_chrono_rag_passes_context_and_uses_base_model(self, shared_rag):
        retriever, adapter = shared_rag
        seen: list[dict] = []
        client = _mock_ollama_client(ollama_up=True, captured_requests=seen)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        res = backend.generate(
            "Học phí tín chỉ chương trình chuẩn năm học 2026-2027 là bao nhiêu?",
            mode="chrono_rag",
            top_k=3,
        )
        assert res["inference_source"] == "ollama_local"
        assert res["engine_mode"] == "OLLAMA_LOCAL"
        assert res["model_name"] == "chronoreg-base:3b"
        assert "570.000" in res["answer"]
        assert len(res["cited_doc_ids"]) >= 1

        chat_reqs = [r for r in seen if r["url"].endswith("/api/chat")]
        assert len(chat_reqs) == 1
        assert chat_reqs[0]["body"]["model"] == "chronoreg-base:3b"
        prompt_sent = chat_reqs[0]["body"]["messages"][0]["content"]
        assert "2377" in prompt_sent or "570.000" in prompt_sent

    def test_tier1_ollama_continual_lora_calls_lora_model_without_doc_context(self, shared_rag):
        retriever, adapter = shared_rag
        seen: list[dict] = []
        client = _mock_ollama_client(ollama_up=True, captured_requests=seen)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        question = "Quy trình bảo lưu kết quả học tập tại UET như thế nào?"
        res = backend.generate(question, mode="continual_lora")
        assert res["inference_source"] == "ollama_local"
        assert res["engine_mode"] == "OLLAMA_LOCAL"
        assert res["model_name"] == "chronoreg-lora:3b"
        assert res["cited_doc_ids"] == []

        chat_reqs = [r for r in seen if r["url"].endswith("/api/chat")]
        assert len(chat_reqs) == 1
        assert chat_reqs[0]["body"]["model"] == "chronoreg-lora:3b"
        assert chat_reqs[0]["body"]["messages"][0]["content"] == f"Năm học được hỏi: 2026-2027.\n{question}"

        # Also verify explicit year detection from question text
        seen.clear()
        q_2024 = "Học phí năm học 2024-2025 là bao nhiêu?"
        backend.generate(q_2024, mode="continual_lora")
        assert seen[-1]["body"]["messages"][0]["content"] == f"Năm học được hỏi: 2024-2025.\n{q_2024}"

    def test_tier1_ollama_naive_rag_uses_base_model(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=True)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        res = backend.generate("Học phí năm học 2026-2027 là bao nhiêu?", mode="naive_rag")
        assert res["inference_source"] == "ollama_local"
        assert res["model_name"] == "chronoreg-base:3b"

    def test_tier2_remote_gpu_used_when_ollama_down(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=False, remote_up=True)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="https://remote-gpu.example/generate",
            http_client=client,
        )
        res = backend.generate(
            "Quy trình bảo lưu kết quả học tập tại UET như thế nào?",
            mode="continual_lora",
        )
        assert res["inference_source"] == "remote_gpu"
        assert res["engine_mode"] == "REMOTE_GPU"
        assert "Remote GPU Tunnel" in res["answer"]

    def test_tier3_cached_fallback_lookup_from_eval_jsonl(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=False, remote_up=False)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        # Exact BENCH_ACT_001 question present in runs/eval/chrono_rag.jsonl
        q = (
            "Mức học phí đào tạo đại học hệ chính quy CTĐT chuẩn đối với sinh viên khóa "
            "QH-2021 trở về trước hiện nay là bao nhiêu tiền một tháng và một tín chỉ?"
        )
        res = backend.generate(q, mode="chrono_rag")
        assert res["inference_source"] == "cached_fallback"
        assert res["engine_mode"] == "CACHED_FALLBACK"
        assert "2.090.000" in res["answer"]
        assert "570.000" in res["answer"]

    def test_tier3_extractive_fallback_for_non_benchmark_question(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=False, remote_up=False)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        res = backend.generate(
            "Học kỳ phụ 2026-2027 từ ngày nào đến ngày nào?",
            mode="chrono_rag",
        )
        assert res["inference_source"] == "cached_fallback"
        assert res["engine_mode"] == "CACHED_FALLBACK"
        assert "05/07/2027" in res["answer"]

    def test_tier3_continual_lora_fallback_never_crashes(self, shared_rag):
        retriever, adapter = shared_rag
        client = _mock_ollama_client(ollama_up=False, remote_up=False)
        backend = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client,
        )
        res = backend.generate(
            "Sinh viên bị cảnh báo học vụ cần làm gì để cải thiện?",
            mode="continual_lora",
        )
        assert res["inference_source"] == "cached_fallback"
        assert res["engine_mode"] == "CACHED_FALLBACK"
        assert len(res["answer"]) > 20


class TestFastAPIIntegrationWithMockOllama:
    def test_health_chat_and_compare_with_mocked_ollama(self, monkeypatch, shared_rag):
        fastapi = pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server

        retriever, adapter = shared_rag
        client_on = _mock_ollama_client(ollama_up=True)
        mock_backend_on = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client_on,
        )
        monkeypatch.setattr(server, "llm_backend", mock_backend_on)

        with TestClient(server.app) as api_client:
            h = api_client.get("/api/health").json()
            assert h["status"] == "ok"
            assert h["ollama_reachable"] is True
            assert h["base_model_ready"] is True
            assert h["lora_model_ready"] is True
            assert h["engine_label"] == "Engine: Ollama 3B Local (Ready)"

            r_rag = api_client.post(
                "/api/chat",
                json={"question": "Học phí tín chỉ chương trình chuẩn năm học 2026-2027 là bao nhiêu?"},
            ).json()
            assert r_rag["metadata"]["inference_source"] == "ollama_local"
            assert "570.000" in r_rag["answer"]

            r_lora = api_client.post(
                "/api/chat",
                json={"question": "Quy trình bảo lưu kết quả học tập tại UET như thế nào?"},
            ).json()
            assert r_lora["routing"]["actual_engine_used"] == "continual_lora"
            assert r_lora["metadata"]["inference_source"] == "ollama_local"

            r_cmp = api_client.post(
                "/api/compare",
                json={"question": "Học phí 2026-2027 là bao nhiêu?"},
            ).json()
            assert r_cmp["chrono_rag"]["metadata"]["inference_source"] == "ollama_local"
            assert r_cmp["continual_lora"]["metadata"]["inference_source"] == "ollama_local"

    def test_health_and_chat_fallback_when_ollama_off(self, monkeypatch, shared_rag):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server

        retriever, adapter = shared_rag
        client_off = _mock_ollama_client(ollama_up=False)
        mock_backend_off = ChronoRegLLMBackend(
            repo_root=ROOT,
            retriever=retriever,
            adapter=adapter,
            remote_url="",
            http_client=client_off,
        )
        monkeypatch.setattr(server, "llm_backend", mock_backend_off)

        with TestClient(server.app) as api_client:
            h = api_client.get("/api/health").json()
            assert h["ollama_reachable"] is False
            assert h["engine_label"] == "Engine: Cached / Extractive Mode"

            r = api_client.post(
                "/api/chat",
                json={"question": "Học phí tín chỉ chương trình chuẩn năm học 2026-2027 là bao nhiêu?"},
            ).json()
            assert r["metadata"]["inference_source"] == "cached_fallback"
            assert "570.000" in r["answer"]


class TestExportOllamaGGUFScript:
    def test_generate_modelfiles_and_instructions(self, tmp_path):
        from scripts.export_to_ollama_gguf import (
            format_deployment_instructions,
            generate_ollama_modelfiles,
            main as export_main,
        )

        ollama_dir = tmp_path / "ollama"
        base_mf, lora_mf = generate_ollama_modelfiles(ollama_dir)
        assert base_mf.is_file()
        assert lora_mf.is_file()

        base_txt = base_mf.read_text(encoding="utf-8")
        lora_txt = lora_mf.read_text(encoding="utf-8")
        assert "FROM ./qwen2.5-3b-instruct-q4_k_m.gguf" in base_txt
        assert "PARAMETER temperature 0.1" in base_txt
        assert "PARAMETER num_ctx 4096" in base_txt
        assert "FROM ./chronoreg-lora-3b-q4_k_m.gguf" in lora_txt
        assert "PARAMETER temperature 0.2" in lora_txt
        assert "PARAMETER num_ctx 2048" in lora_txt
        assert "Bạn là trợ lý học vụ UET. Trả lời ngắn, đúng phạm vi câu hỏi; không bịa quy định hay năm hiệu lực." in lora_txt

        rc = export_main([
            "--modelfiles-only",
            "--ollama-dir", str(tmp_path / "ollama2"),
            "--output-dir", str(tmp_path / "merged"),
        ])
        assert rc == 0
        guide = format_deployment_instructions("Qwen/Qwen2.5-3B-Instruct", tmp_path / "merged", ollama_dir)
        assert "convert_hf_to_gguf.py" in guide
        assert "llama-quantize" in guide
        assert "Q4_K_M" in guide
        assert "ollama create chronoreg-base:3b -f Modelfile.base" in guide
        assert "ollama create chronoreg-lora:3b -f Modelfile.lora" in guide

