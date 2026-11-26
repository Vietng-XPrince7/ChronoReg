import pytest
import json

# Graceful skip if FastAPI/httpx not installed or server not built
api_available = False
try:
    from fastapi.testclient import TestClient
    from src.api.studenthub_server import app
    api_available = True
except (ImportError, Exception):
    pass

pytestmark = pytest.mark.skipif(not api_available, reason="FastAPI server not available")

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.api.studenthub_server import app
    return TestClient(app)

class TestChatEndpoint:
    def test_chat_returns_200(self, client):
        r = client.post("/api/chat", json={"question": "Học phí 2026 là bao nhiêu?"})
        assert r.status_code == 200

    def test_chat_response_has_required_keys(self, client):
        r = client.post("/api/chat", json={"question": "Học phí 2026 là bao nhiêu?"})
        d = r.json()
        assert "question" in d
        assert "routing" in d
        assert "answer" in d
        assert "metadata" in d

    def test_chat_routing_has_engine(self, client):
        r = client.post("/api/chat", json={"question": "Quy trình bảo lưu?"})
        d = r.json()
        assert d["routing"]["selected_engine"] in ("chrono_rag", "continual_lora", "safety_gate_red", "naive_rag", "meta_greeting")

    def test_chat_greeting_returns_intro(self, client):
        r = client.post("/api/chat", json={"question": "xin chào"})
        assert r.status_code == 200
        d = r.json()
        assert d["routing"]["selected_engine"] == "meta_greeting"
        assert "ChronoReg" in d["answer"]
        assert d["metadata"]["doc_id"] is None
        assert d["metadata"]["source_type"] == "meta_greeting"

    def test_chat_lora_metadata_has_no_rag_doc(self, client):
        r = client.post(
            "/api/chat",
            json={
                "question": "Quy trình bảo lưu kết quả học tập tại UET như thế nào?",
                "force_engine": "continual_lora",
            },
        )
        assert r.status_code == 200
        d = r.json()
        assert d["routing"]["actual_engine_used"] == "continual_lora"
        assert d["metadata"]["doc_id"] is None
        assert d["metadata"]["sha256_short"] is None
        em = d["metadata"]["engine_mode"]
        expected = {
            "LIVE_PEFT_GENERATION": "lora_parametric",
            "OLLAMA_LOCAL": "lora_ollama_local",
            "REMOTE_GPU": "lora_remote_gpu",
            "CACHED_FALLBACK": "lora_cached_fallback",
        }.get(em, "lora_unavailable")
        assert d["metadata"]["source_type"] == expected
        assert "inference_source" in d["metadata"]
        assert d["metadata"]["quality_qualified"] is False

    def test_chat_auto_falls_back_to_rag_when_lora_unavailable(self, client):
        from src.api.studenthub_server import web_lora
        if web_lora.status().get("ready"):
            pytest.skip("LoRA V3 is ready on this machine")
        r = client.post("/api/chat", json={"question": "Quy trình bảo lưu kết quả học tập tại UET như thế nào?"})
        assert r.status_code == 200
        d = r.json()
        assert d["routing"]["selected_engine"] == "continual_lora"
        assert d["routing"]["actual_engine_used"] in ("chrono_rag", "continual_lora")
        assert d["metadata"].get("engine_note")
        assert len(d["answer"]) > 30

    def test_chat_force_engine_chrono_rag(self, client):
        r = client.post("/api/chat", json={"question": "Học phí?", "force_engine": "chrono_rag"})
        d = r.json()
        assert d["routing"]["actual_engine_used"] in ("chrono_rag", "naive_rag")

    def test_chat_safety_gate_blocked(self, client):
        r = client.post("/api/chat", json={"question": "Xin cứu xét ngoại lệ miễn học phí"})
        assert r.status_code == 200
        d = r.json()
        assert d["routing"]["selected_engine"] == "safety_gate_red"
        assert d["routing"]["risk_tier"] == "RED"

    def test_chat_answer_not_empty(self, client):
        r = client.post("/api/chat", json={"question": "Học phí 2026?"})
        d = r.json()
        assert len(d["answer"]) > 5

class TestCompareEndpoint:
    def test_compare_returns_200(self, client):
        r = client.post("/api/compare", json={"question": "Học phí 2026?"})
        assert r.status_code == 200

    def test_compare_has_all_engines(self, client):
        r = client.post("/api/compare", json={"question": "Học phí 2026?"})
        d = r.json()
        assert "chrono_rag" in d
        assert "continual_lora" in d
        assert "naive_rag" in d

    def test_compare_safety_gate_blocked(self, client):
        r = client.post("/api/compare", json={"question": "Tôi muốn xin cứu xét ngoại lệ miễn học phí"})
        assert r.status_code == 200
        d = r.json()
        assert d["chrono_rag"]["routing"]["risk_tier"] == "RED"
        assert d["chrono_rag"]["routing"]["selected_engine"] == "safety_gate_red"
        assert d["continual_lora"]["routing"]["risk_tier"] == "RED"
        assert "Cổng An toàn" in d["chrono_rag"]["answer"]

class TestSampleQuestions:
    def test_sample_questions_returns_6(self, client):
        r = client.get("/api/sample-questions")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 6

    def test_sample_questions_have_required_keys(self, client):
        r = client.get("/api/sample-questions")
        for q in r.json():
            assert "question" in q
            assert "category" in q
            assert "hint" in q

    def test_sample_questions_cover_all_categories(self, client):
        r = client.get("/api/sample-questions")
        categories = {q["category"] for q in r.json()}
        assert "lora_strength" in categories
        assert "rag_strength" in categories
        assert "red_gate" in categories
