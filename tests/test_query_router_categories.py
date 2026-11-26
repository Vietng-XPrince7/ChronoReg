"""Unit & scoping tests for the 6-category Advisor Query Router."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo.class_roster import NGHE_SI_30, generate_class_roster
from src.router.query_router import build_context, classify_query


@pytest.fixture(scope="module")
def sample_roster(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("router_roster")
    return generate_class_roster(seed=42, save_dir=tmp_dir)


STUDENT_STATUS_CASES = [
    ("Kiểm tra tình trạng học tập của sinh viên Sơn Tùng MTP (24020001)?", None, "24020001"),
    ("Em Nguyễn Hà Anh Tuấn học thế nào?", None, "24020004"),
    ("Phan Mạnh Quỳnh có đủ điều kiện xét học bổng KKHT kỳ này không?", None, "24020007"),
    ("Sinh viên 24020027 hiện đang nợ bao nhiêu tín chỉ và có bị cảnh báo không?", None, "24020027"),
    ("Xem giúp bảng điểm và CPA của Vũ Cát Tường", None, "24020003"),
    ("Bạn 24020013 có đủ điều kiện đăng ký học vượt 24 tín chỉ không?", None, "24020013"),
    ("Tình trạng học vụ của sinh viên này thế nào?", "24020019", "24020019"),
    ("Em Nguyễn Trúc Nhân bị trượt học bổng vì lý do gì?", None, "24020008"),
]

CLASS_STATS_CASES = [
    "Thống kê GPA trung bình và phân bố học lực của lớp mình kỳ này?",
    "Lớp có bao nhiêu sinh viên, môn nào bị trượt nhiều nhất?",
    "Tóm tắt tình hình học tập chung của cả lớp QH-2024-I/CQ-C-CLC1",
    "Cho tôi xem top môn học có tỷ lệ trượt cao nhất trong lớp",
    "Phân tích tổng quan điểm rèn luyện và điểm trung bình toàn lớp",
    "Trong lớp có bao nhiêu môn cả lớp đều qua và môn nào trượt nhiều?",
    "Thống kê số lượng sinh viên từng nhóm học lực của lớp mình",
    "Lớp K69-CNTT1 có bao nhiêu lượt trượt ở môn Giải tích 2?",
]

COURSE_TREND_CASES = [
    "Dự đoán học kỳ tới môn nào sẽ khó và có nhiều sinh viên trượt nhất?",
    "Theo xu hướng các năm trước, môn INT2215 kỳ tới tỷ lệ qua môn thế nào?",
    "So sánh độ khó môn Giải tích 1 qua các khóa trước để tư vấn đăng ký kỳ tới?",
    "Xu hướng điểm trung bình môn Mạng máy tính qua các học kỳ gần đây ra sao?",
    "Kỳ tới những môn nào trong chương trình dễ bị rớt nhất dựa theo lịch sử các khóa?",
    "Dự báo xu hướng trượt môn Cấu trúc dữ liệu và giải thuật trong năm học tới?",
]

EVENT_NEWS_CASES = [
    "Trên trang chủ UET có thông báo tin tức mới nhất nào cho sinh viên không?",
    "Cập nhật các sự kiện và hội thảo học thuật vừa đăng trên cổng thông tin UET",
    "Tin tức mới nhất từ phòng Đào tạo và CTSV về lịch đăng ký tín chỉ",
    "Nhà trường mới có thông báo nào về học bổng tài trợ doanh nghiệp tuần này?",
    "Tóm tắt các bài viết mới nhất trang 1 cổng thông tin sinh viên UET",
    "Kiểm tra giúp xem UET vừa đăng thông báo gì mới hôm nay?",
]

ELIGIBILITY_CHECK_CASES = [
    "Soi bảng điểm lớp mình kỳ này, liệt kê những em đủ điều kiện xét học bổng KKHT và chỉ rõ em nào bị trượt vì điểm rèn luyện?",
    "Trong lớp hiện có những sinh viên nào thuộc diện nguy cơ cảnh báo học vụ?",
    "Lớp mình ai đủ điều kiện đăng ký học vượt lên tới 24 tín chỉ ở kỳ tới?",
    "Kiểm tra danh sách sinh viên lớp mình bị bẫy ĐRL dưới 70 nên mất học bổng",
    "Những em nào trong lớp đạt mức GPA từ 3.6 trở lên nhưng chưa đủ ĐRL xét KKHT?",
    "Rà soát toàn lớp xem ai bị đình chỉ học tập hoặc cảnh báo học vụ kỳ này",
    "Lớp có em nào đang xin học vượt 24 tín chỉ và ai đủ điều kiện được duyệt?",
]

REGULATION_CASES = [
    "Quy định miễn giảm học phí cho sinh viên diện hộ nghèo năm học 2026-2027 là gì?",
    "Điều kiện xét học bổng khuyến khích học tập theo quy chế UET hiện hành?",
    "Thủ tục xin bảo lưu kết quả học tập cần những giấy tờ gì và nộp ở đâu?",
    "Quy chế cảnh báo học vụ và buộc thôi học áp dụng ngưỡng GPA bao nhiêu?",
    "Hướng dẫn quy trình xin phúc khảo điểm thi kết thúc học phần?",
    "Mức trần học phí chương trình chuẩn CNTT của UET năm 2025-2026 là bao nhiêu?",
    "Sinh viên đăng ký tối đa bao nhiêu tín chỉ mỗi học kỳ nếu học lực bình thường?",
    "Thời hạn đóng học phí và hậu quả khi chậm đóng quá thời hạn quy định?",
]


class TestQueryRouterClassification:
    @pytest.mark.parametrize("question,explicit_mssv,expected_mssv", STUDENT_STATUS_CASES)
    def test_student_status_category(self, sample_roster, question, explicit_mssv, expected_mssv):
        category, entities = classify_query(question, roster=sample_roster, mssv=explicit_mssv)
        assert category == "STUDENT_STATUS"
        assert entities["mssv"] == expected_mssv

    @pytest.mark.parametrize("question", CLASS_STATS_CASES)
    def test_class_stats_category(self, sample_roster, question):
        category, entities = classify_query(question, roster=sample_roster)
        assert category == "CLASS_STATS"
        assert entities["mssv"] is None

    @pytest.mark.parametrize("question", COURSE_TREND_CASES)
    def test_course_trend_category(self, sample_roster, question):
        category, _ = classify_query(question, roster=sample_roster)
        assert category == "COURSE_TREND"

    @pytest.mark.parametrize("question", EVENT_NEWS_CASES)
    def test_event_news_category(self, sample_roster, question):
        category, _ = classify_query(question, roster=sample_roster)
        assert category == "EVENT_NEWS"

    @pytest.mark.parametrize("question", ELIGIBILITY_CHECK_CASES)
    def test_eligibility_check_category(self, sample_roster, question):
        category, entities = classify_query(question, roster=sample_roster)
        assert category == "ELIGIBILITY_CHECK"
        assert entities["mssv"] is None

    @pytest.mark.parametrize("question", REGULATION_CASES)
    def test_regulation_category(self, sample_roster, question):
        category, entities = classify_query(question, roster=sample_roster)
        assert category == "REGULATION"
        assert entities["mssv"] is None


class TestQueryRouterBuildContext:
    def test_student_status_build_context_never_leaks_other_students(self, sample_roster):
        target_mssv = "24020004"
        target_name = "Nguyễn Hà Anh Tuấn"
        category, entities = classify_query(f"Em {target_name} học thế nào?", roster=sample_roster)
        assert category == "STUDENT_STATUS"

        ctx = build_context(category, entities, roster=sample_roster)
        assert ctx["category"] == "STUDENT_STATUS"
        assert ctx["use_rag"] is False
        assert ctx["use_lora"] is False

        data = ctx["data"]
        assert data["mssv"] == target_mssv
        assert data["ho_ten"] == target_name
        assert "students" not in data
        assert "danh_sach" not in data

        serialized = json.dumps(ctx, ensure_ascii=False)
        for other_id, other_name, _ in NGHE_SI_30:
            if other_id != target_mssv:
                assert other_id not in serialized
                assert other_name not in serialized

    def test_class_stats_and_eligibility_contexts_are_distinct(self, sample_roster):
        c1, e1 = classify_query("Thống kê GPA trung bình và môn trượt nhiều nhất lớp?", roster=sample_roster)
        ctx1 = build_context(c1, e1, roster=sample_roster)
        assert ctx1["category"] == "CLASS_STATS"
        assert ctx1["use_rag"] is False
        assert ctx1["data"]["total_students"] == 30
        assert "class_id" in ctx1["data"]

        c2, e2 = classify_query("Lớp mình ai đủ điều kiện học bổng KKHT?", roster=sample_roster)
        ctx2 = build_context(c2, e2, roster=sample_roster)
        assert ctx2["category"] == "ELIGIBILITY_CHECK"
        assert ctx2["use_rag"] is True
        assert "step1_regulation_rule" in ctx2["data"]
        assert "step2_class_summary" in ctx2["data"]

    def test_course_trend_states_insufficient_historical_data(self, sample_roster):
        c, e = classify_query("Dự đoán kỳ tới môn nào khó và dễ trượt nhất?", roster=sample_roster)
        assert c == "COURSE_TREND"
        ctx = build_context(c, e, roster=sample_roster)
        assert ctx["use_rag"] is False
        assert ctx["use_lora"] is False
        assert ctx["data"]["sufficient_historical_data"] is False
        assert "chưa đủ dữ liệu" in ctx["context_text"].lower()

    def test_event_news_and_regulation_do_not_attach_roster(self, sample_roster):
        mock_news = {
            "fetched_at": "2026-11-26T10:00:00+07:00",
            "source": "live_scrape",
            "articles": [{"title": "Thông báo mới UET", "date": "26/11/2026", "summary": "Chi tiết.", "url": "https://uet.edu.vn/1"}],
        }
        c_news, e_news = classify_query("Tin tức mới nhất trên UET?", roster=sample_roster)
        ctx_news = build_context(c_news, e_news, roster=sample_roster, news_payload=mock_news)
        assert "Thông báo mới UET" in ctx_news["context_text"]
        assert "Sơn Tùng MTP" not in ctx_news["context_text"]

        c_reg, e_reg = classify_query("Thủ tục xin bảo lưu kết quả học tập?", roster=sample_roster)
        ctx_reg = build_context(c_reg, e_reg, roster=sample_roster)
        assert ctx_reg["category"] == "REGULATION"
        assert ctx_reg["use_rag"] is True
        assert ctx_reg["use_lora"] is True
        assert ctx_reg["data"] == {}
        assert ctx_reg["context_text"] == ""

