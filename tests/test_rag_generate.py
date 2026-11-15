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
