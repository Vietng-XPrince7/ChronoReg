"""Kiểm thử dựng prompt và chọn provider sinh câu trả lời (không cần model thật)."""
from unittest.mock import patch

import pytest

from src.rag import generate as g
from src.rag.versioning import VersionPlan


def _hit(doc_id, year, text, status="verified", dieu=""):
    return {"document": text, "distance": 0.1, "metadata": {
        "doc_id": doc_id, "academic_year": year, "year_status": status, "dieu_so": dieu}}


HITS = [_hit("hp-2025", "2025-2026", "Mức học phí 1.850.000 đồng/tháng. " * 100),
        _hit("hp-2026", "2026-2027", "Mức học phí 2.090.000 đồng/tháng.", dieu="Điều 2"),
        _hit("hp-x", "", "Đoạn chưa rõ năm", status="unknown")]


def test_prompt_contains_scope_years_and_trims_context():
    plan = VersionPlan("year", 2026, "x", (2026, 2025))
    user = g.build_user("Học phí là bao nhiêu?", HITS, plan, max_hits=2, max_chars=200)
    assert "2026-2027 và 2025-2026" in user
    assert "NĂM HỌC 2026-2027" in user and "NĂM HỌC 2025-2026" in user
    assert "hp-2026 - Điều 2 - năm học 2026-2027" in user
    assert "hp-x" not in user                         # vượt max_hits
    assert len(user) < 900                            # đoạn dài bị cắt
    assert user.rstrip().endswith("=== TRẢ LỜI ===")
    assert "(chưa duyệt)" in g.build_user("q", HITS, plan)   # chunk chưa duyệt được ghi rõ


def test_system_prompt_tells_the_model_to_write_its_own_answer():
    assert "bằng lời của bạn" in g.SYSTEM and "Không tìm thấy thông tin" in g.SYSTEM
    assert "không lấy mức của năm này để trả lời cho năm khác" in g.SYSTEM


def test_provider_none_returns_retrieved_text():
    out = g.generate("q", HITS, VersionPlan("all", None, "x"), {"llm": {"provider": "none"}})
    assert "hp-2025" in out and "hp-x" not in out


def test_provider_local_calls_the_model_with_system_and_user():
    seen = {}

    def fake_chat(provider, system, user, llm):
        seen.update(provider=provider, system=system, user=user, llm=llm)
        return "Câu trả lời do model viết."

    cfg = {"llm": {"provider": "local", "model": "m", "max_hits": 2, "max_context_chars": 50}}
    with patch.object(g, "_chat", fake_chat):
        out = g.generate("Học phí?", HITS, VersionPlan("latest", 2026, "x", (2026,)), cfg)
    assert out == "Câu trả lời do model viết."
    assert seen["provider"] == "local" and seen["system"] == g.SYSTEM
    assert "mới nhất" in seen["user"] and "Học phí?" in seen["user"]


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        g._chat("khong-co", "s", "u", {})


def test_provider_gemini_rest_payload_and_response(monkeypatch, tmp_path):
    import io
    import json
    import urllib.request

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=test-gemini-key-123\n", encoding="utf-8")
    g.load_dotenv_if_present(env_file)

    captured = {}

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "candidates": [{
                    "content": {
                        "parts": [
                            {"thought": True, "text": "internal reasoning"},
                            {"text": "Theo Quyết định 2377/QĐ-ĐHCN năm học 2026-2027, mức học phí là 2.090.000 đồng/tháng."},
                        ]
                    }
                }]
            }).encode("utf-8")

    def fake_urlopen(req, timeout=30.0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    cfg = {"llm": {"provider": "gemini", "model": "gemini-2.5-flash", "max_new_tokens": 500, "temperature": 0.1}}
    out = g.generate("Học phí là bao nhiêu?", HITS, VersionPlan("latest", 2026, "x", (2026,)), cfg)

    assert "2.090.000 đồng/tháng" in out
    assert "internal reasoning" not in out
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "test-gemini-key-123"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == g.SYSTEM
    assert captured["body"]["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0


def test_provider_gemini_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.setattr(g, "_DOTENV_LOADED", True)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        g._gemini_chat("sys", "usr", {"model": "gemini-2.5-flash"})


def test_dotenv_utf8_bom_and_placeholder_rejection(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    # 1. Placeholder Vietnamese text written with UTF-8 BOM must be rejected as unusable
    env_ph = tmp_path / ".env_ph"
    env_ph.write_bytes(b"\xef\xbb\xbfGEMINI_API_KEY=D\xc3\x81N_API_KEY_C\xe1\xbb\xa6A_B\xe1\xba\xa0N_V\xc3\x80O_\xc4\x90\xc3\x82Y\n")
    g.load_dotenv_if_present(env_ph)
    assert g.resolve_gemini_api_key({}) == ""
    assert g.has_llm_credentials({"llm": {"provider": "gemini"}}) is False

    # 2. Real ASCII key written with UTF-8 BOM is stripped cleanly and accepted
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_real = tmp_path / ".env_real"
    env_real.write_bytes(b"\xef\xbb\xbfGEMINI_API_KEY=AIzaSyTestValidAsciiKey12345\n")
    g.load_dotenv_if_present(env_real)
    assert g.resolve_gemini_api_key({}) == "AIzaSyTestValidAsciiKey12345"
    assert g.has_llm_credentials({"llm": {"provider": "gemini"}}) is True
