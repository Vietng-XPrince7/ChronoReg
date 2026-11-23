from fastapi.testclient import TestClient
from src.api.studenthub_server import app

client = TestClient(app)


def test_legacy_red_override_blocked():
    response = client.post('/api/chat', json={
        "question": "Xin cứu xét ngoại lệ miễn học phí",
        "force_engine": "continual_lora"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["routing"]["risk_tier"] == "RED"
    assert payload["routing"]["actual_engine_used"] == "safety_gate_red"


def test_new_endpoint_no_fake_lora():
    response = client.post('/api/answer-v2', json={
        "question": "Cần nộp hồ sơ bảo lưu năm 2026 ra sao?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_engine"] in {"chrono_rag", "abstain"}
    assert not payload.get("authoritative_regulation_answer", False)


def test_new_endpoint_explainer_is_not_official_regulation():
    response = client.post('/api/answer-v2', json={
        "question": "Cho mình cách học hiệu quả"})
    assert response.status_code == 200
    assert not response.json()["authoritative_regulation_answer"]


def test_new_endpoint_red_honored():
    response = client.post('/api/answer-v2', json={
        "question": "Xin cứu xét ngoại lệ miễn học phí", "compare": True})
    assert response.status_code == 200
    assert response.json()["selected_engine"] == "abstain"
    assert "comparison" not in response.json()
