"""Topic detection, temporal intent parsing, and calendar-date extraction for ChronoReg RAG."""
from __future__ import annotations

import re

from .lexicon import _normalize_query_typos


def detect_topic(question: str) -> str:
    """Infer canonical topic aligned with src/versioning/core.py TOPICS and curricula."""
    ql = _normalize_query_typos(question).lower()
    asks_policy = any(k in ql for k in (
        "học phí", "mức thu", "định mức", "đồng/", "đóng", "nộp", "tạm thu", "học bổng", "kkht", "tài trợ",
        "kế hoạch học tập", "lịch nghỉ", "thời khóa biểu", "xét tốt nghiệp", "gdqpan", "quân sự", "hội nghị", "nckh", "svnckh",
        "học lại", "cải thiện", "bằng kép", "kéo dài", "điểm chuẩn", "điểm trúng tuyển", "xét tuyển",
    ))
    if not asks_policy and (
        any(k in ql for k in (
            "kỹ thuật năng lượng", "vật lý kỹ thuật", "cơ kỹ thuật", "cơ học kỹ thuật",
            "công nghệ hàng không", "kỹ thuật không gian", "điều khiển và tự động hóa",
            "hệ thống thông tin", "khoa học máy tính", "khoa học dữ liệu", "mạng máy tính",
            "kỹ thuật máy tính", "kỹ thuật robot", "công nghệ vật liệu", "kỹ thuật vật liệu",
            "kỹ thuật xây dựng", "công nghệ sinh học", "công nghệ kỹ thuật điện tử",
            "điện tử - viễn thông", "điện tử viễn thông", "công nghệ nông nghiệp",
            "công nghệ thông tin", "trí tuệ nhân tạo", "thiết kế công nghiệp",
            "cơ điện tử", "chuẩn đầu ra", "plo", "mục tiêu đào tạo",
            "vị trí việc làm", "cơ hội việc làm", "gồm bao nhiêu tín chỉ", "tổng số tín chỉ",
            "chương trình đào tạo ngành", "ctđt ngành", "khung chương trình",
            "có những môn học nào", "học những môn gì", "những môn học nào", "các học phần nào",
        ))
        or (
            bool(re.search(r"\bngành\s+\S+", ql))
            and any(k in ql for k in ("môn học", "môn gì", "học phần", "tín chỉ", "việc làm", "nghề nghiệp", "chương trình", "ctđt", "định hướng"))
        )
        or bool(re.search(r"\b(?:môn(?:\s+học)?|học\s+phần)\s+(?!học\b|nào\b|gì\b|này\b|đó\b)\S+", ql))
        or bool(re.search(r"\b(?:uet\.)?[a-z]{3}\d{4}\b", ql))
    ):
        return "curriculum"
    if any(k in ql for k in (
        "kế hoạch học tập", "kế hoạch đào tạo", "khung thời gian", "lịch nghỉ tết", "nghỉ tết nguyên đán",
        "thời khóa biểu", "xét tốt nghiệp", "tuần 1 học chuyên môn", "456/kh-đhcn", "gdqpan", "quân sự",
        "khóa luận tốt nghiệp", "giờ học", "buổi sáng", "buổi chiều", "buổi tối", "tiết học",
    )) or bool(re.search(r"\btiết\s+\d+\b", ql)):
        return "academic_calendar"
    if any(k in ql for k in (
        "học phí", "mức thu", "định mức kinh tế", "kinh tế kỹ thuật",
        "đồng/tháng", "đồng/tín chỉ", "miễn giảm học phí", "tạm thu", "thu học phí", "nộp học phí", "347/qđ-khtc",
    )):
        return "tuition"
    if any(k in ql for k in (
        "học bổng", "kkht", "khuyến khích học tập", "tài trợ", "khen thưởng",
    )):
        return "scholarship"
    if any(k in ql for k in (
        "nghiên cứu khoa học", "svnckh", "nckh", "poster", "đề tài khoa học", "sinh viên nghiên cứu",
    )):
        return "research"
    if any(k in ql for k in (
        "điểm chuẩn", "điểm trúng tuyển", "xét tuyển", "chỉ tiêu tuyển sinh",
        "nguyện vọng", "nhập học", "đề án tuyển sinh",
    )):
        return "admissions"
    if any(k in ql for k in (
        "lịch trình", "nghỉ tết", "tuần học", "tuần 1", "học kỳ phụ", "học kỳ hè",
    )):
        return "academic_calendar"
    if any(k in ql for k in (
        "quy chế đào tạo", "cảnh báo học tập", "cảnh báo học vụ", "buộc thôi học",
        "khóa luận", "học phần", "điểm trung bình", "cpa", "gpa", "nghỉ học tạm thời",
        "bảo lưu", "chuyển ngành", "song ngành",
    )):
        return "training_rules"
    return ""


def parse_temporal_intent(question: str, as_of_year: int | None = None) -> tuple[str, int | None]:
    """Detect temporal category and target academic start year (Zero-Oracle)."""
    q = _normalize_query_typos(question).lower()
    is_superseded = any(kw in q for kw in (
        "cũ", "trước đây", "trước kia", "trước năm", "trước khi",
        "thay thế", "thay đổi", "hết hiệu lực", "không còn hiệu lực",
        "trước đó", "bản cũ", "so sánh", "sửa đổi", "bãi bỏ", "hủy bỏ", "không còn áp dụng",
    ))
    is_active = any(kw in q for kw in (
        "hiện nay", "hiện hành", "mới nhất", "hiện tại", "đang áp dụng",
    ))

    academic_years = [
        int(m.group(1))
        for m in re.finditer(r"(?<!qh-)(?<!qh)\b(202\d)\s*[-–—/]\s*(202\d)\b", q)
        if int(m.group(2)) == int(m.group(1)) + 1
    ]
    date_years = [
        int(m.group(1))
        for m in re.finditer(r"\b\d{1,2}[/-]\d{1,2}[/-](202\d)\b", q)
    ]
    context_years = [
        int(m.group(1))
        for m in re.finditer(r"(?<!khóa\s)(?<!khoá\s)(?:năm\s*học|áp dụng(?:\s*cho)?\s*năm|ban\s*hành\s*năm|năm)\s*(202\d)\b", q)
    ]

    isolated_years: list[int] = []
    for m in re.finditer(r"\b(202\d)\b", q):
        start = m.start()
        prefix = q[max(0, start - 28) : start].strip()
        if not re.search(
            r"(?:khóa|khoá|qh-|qh\s*|k|k-|tuyển\s+sinh\s+năm|tuyển\s+sinh\s+mới\s+năm|tuyển\s+sinh\s+từ|tuyển\s+sinh\s+từ\s+năm|trúng\s+tuyển\s+trong\s+các\s+năm|tuyển\s+sinh)$",
            prefix,
        ):
            isolated_years.append(int(m.group(1)))

    if is_superseded:
        m_truoc_range = re.search(r"trước\s+(?:năm\s*học|năm|khi)\s*(202\d)\s*[-–—/]\s*(202\d)", q)
        m_truoc_single = re.search(r"trước\s+(?:năm\s*học|năm|khi[^0-9]{0,25})\s*(202\d)\b", q)
        if len(academic_years) >= 2:
            det_y = min(academic_years)
        elif m_truoc_range:
            det_y = int(m_truoc_range.group(1)) - 1
        elif m_truoc_single and len(isolated_years) == 1:
            det_y = int(m_truoc_single.group(1)) - 1
        elif academic_years:
            det_y = academic_years[0]
        elif context_years:
            det_y = min(context_years)
        elif date_years:
            det_y = min(date_years)
        elif isolated_years:
            det_y = min(isolated_years)
        else:
            det_y = as_of_year
        return "superseded_rule", det_y

    if as_of_year is not None:
        return "temporal_specific", as_of_year

    if academic_years:
        return "temporal_specific", academic_years[0]
    if date_years:
        return "temporal_specific", date_years[0]
    if context_years:
        return "temporal_specific", context_years[0]
    if isolated_years and not is_active:
        return "temporal_specific", isolated_years[0]

    return "active_rule", None


def extract_as_of_date(question: str) -> tuple[str | None, bool]:
    """Extract an explicit calendar date ('tính đến / vào / tại / trước ngày dd/mm/yyyy') as ISO YYYY-MM-DD."""
    ql = _normalize_query_typos(question).lower()
    m = re.search(
        r"\b(tính\s+đến|vào|tại|trước|kể\s+từ|từ)\s+ngày\s+(\d{1,2})[/-](\d{1,2})[/-](202\d)\b",
        ql,
    )
    if not m:
        return None, False
    qual = m.group(1)
    dd, mm, yyyy = int(m.group(2)), int(m.group(3)), int(m.group(4))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None, False
    if "từ" in qual:
        return None, False
    return f"{yyyy:04d}-{mm:02d}-{dd:02d}", ("trước" in qual)
