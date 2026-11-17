import pytest
from pathlib import Path

# Graceful skip if router not yet built
router_available = False
try:
    from src.router.query_router import AdaptiveQueryRouter, RoutingAnalysis
    router_available = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not router_available, reason="src/router/query_router.py not yet built")

@pytest.fixture(scope="module")
def router():
    return AdaptiveQueryRouter()

class TestRoutingDecision:
    def test_quantitative_routes_to_chrono_rag(self, router):
        r = router.route_decision("Học phí tín chỉ chương trình chuẩn năm 2026 là bao nhiêu?")
        assert r.selected_engine == "chrono_rag"
        assert r.risk_tier in ("GREEN", "YELLOW")

    def test_temporal_signal_routes_to_chrono_rag(self, router):
        r = router.route_decision("Mức thu học phí năm học 2025-2026 là bao nhiêu?")
        assert r.selected_engine == "chrono_rag"

    def test_comparison_routes_to_chrono_rag_yellow(self, router):
        r = router.route_decision("Quy định học phí năm 2023 khác gì so với năm 2026?")
        assert r.selected_engine == "chrono_rag"
        assert r.risk_tier == "YELLOW"

    def test_procedural_routes_to_continual_lora(self, router):
        r = router.route_decision("Quy trình bảo lưu kết quả học tập tại UET như thế nào?")
        assert r.selected_engine == "continual_lora"
        assert r.risk_tier == "GREEN"

    def test_advisory_routes_to_continual_lora(self, router):
        r = router.route_decision("Sinh viên bị cảnh báo học vụ cần làm gì để cải thiện?")
        assert r.selected_engine == "continual_lora"

    def test_exception_request_blocked(self, router):
        r = router.route_decision("Xin cứu xét ngoại lệ miễn học phí do hoàn cảnh khó khăn")
        assert r.selected_engine == "safety_gate_red"
        assert r.risk_tier == "RED"

    def test_exception_request_blocked_variation(self, router):
        r = router.route_decision("Tôi xin đặc cách bảo lưu thêm 1 năm")
        assert r.selected_engine == "safety_gate_red"

    def test_routing_analysis_has_all_fields(self, router):
        r = router.route_decision("Học bổng KKHT mới nhất điều kiện gì?")
        assert isinstance(r, RoutingAnalysis)
        assert hasattr(r, "selected_engine")
        assert hasattr(r, "risk_tier")
        assert hasattr(r, "detected_signals")
        assert isinstance(r.detected_signals, list)
        assert hasattr(r, "routing_reason")
        assert hasattr(r, "lora_pros_cons")
        assert hasattr(r, "rag_pros_cons")
        assert len(r.routing_reason) > 20

    def test_student_context_accepted(self, router):
        r = router.route_decision(
            "Học phí của tôi năm nay là bao nhiêu?",
            student_context={"cohort": "QH-2023"}
        )
        assert r.selected_engine in ("chrono_rag", "continual_lora", "safety_gate_red")

    def test_lora_scholarship_check(self, router):
        r = router.route_decision("Mức học bổng KKHT năm 2026 là bao nhiêu triệu?")
        assert r.selected_engine == "chrono_rag"

    def test_current_year_temporal_signal(self, router):
        r = router.route_decision("Hiện hành quy định học phí ra sao?")
        assert r.selected_engine == "chrono_rag"

    def test_greeting_routes_to_meta_greeting(self, router):
        for q in ["xin chào", "hi bot", "bạn là ai", "bạn làm được gì", "m biết làm gì"]:
            r = router.route_decision(q)
            assert r.selected_engine == "meta_greeting"
            assert r.risk_tier == "GREEN"
            assert "Chào hỏi" in r.detected_signals[0]

    def test_long_query_with_greeting_words_not_hijacked(self, router):
        q = "Cho hỏi thủ tục giới thiệu về hệ thống tín chỉ và hỗ trợ gì được cho sinh viên năm 2025?"
        r = router.route_decision(q)
        assert r.selected_engine != "meta_greeting"

    def test_legitimate_fee_waiver_not_blocked_by_red_gate(self, router):
        q1 = "Thủ tục xin miễn giảm học phí cho sinh viên thuộc diện chính sách năm học 2025-2026?"
        q2 = "Em xin miễn học phần Giáo dục thể chất vì đã có chứng chỉ thì quy trình thế nào?"
        assert router.route_decision(q1).selected_engine == "chrono_rag"
        assert router.route_decision(q2).selected_engine != "safety_gate_red"
