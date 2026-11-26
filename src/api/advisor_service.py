"""Advisor pre-check & scoped context builders for UET Academic Advisor Copilot.

Separates single-student pre-check (`precheck_single_student`) from whole-class
pre-check (`precheck_class_summary`) so asking about 1 student never leaks all 30 students.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from src.demo.class_roster import (
    analyze_class_roster,
    format_roster_facts_text,
    load_class_roster,
)

_ROSTER_ANALYSIS_PHRASES = (
    "bảng điểm",
    "soi bảng điểm",
    "soi điểm",
    "lớp mình",
    "lớp tôi",
    "lớp k68",
    "lớp k69",
    "k68-cntt1",
    "k69-cntt1",
    "qh-2024-i/cq-c-clc1",
    "30 sinh viên",
    "em nào",
    "những em nào",
    "sinh viên nào",
    "trong lớp có",
    "trong lớp",
    "xét học bổng",
    "học vượt",
    "bị trượt",
    "cảnh báo học vụ",
)

_PURE_PROCEDURAL_OVERRIDE = (
    "quy trình",
    "thủ tục",
    "gồm những bước nào",
    "bảo lưu",
    "rút bớt học phần",
)

_NEWS_PHRASES = (
    "thông báo mới",
    "vừa cào",
    "trang chủ uet",
    "tin tức",
    "tin mới",
    "trang 1",
    "nộp hồ sơ",
    "nhắc các em",
    "sự kiện gì",
    "sắp tới có sự kiện",
)

_STUDENT_ID_RE = re.compile(r"\b(2402\d{4}|2302\d{4})\b")


def precheck_single_student(mssv: str, roster: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Return deterministic eligibility & grade summary for EXACTLY ONE student by MSSV."""
    active_roster = roster if roster is not None else load_class_roster()
    courses_map = {c["ma_mon"]: c for c in active_roster.get("courses", [])}
    target_id = (mssv or "").strip()

    for st in active_roster.get("students", []):
        if st.get("student_id") == target_id or st.get("mssv") == target_id:
            ev = st.get("assessment") or {}
            failed_courses = [
                {
                    "ma_mon": g["ma_mon"],
                    "ten_mon": courses_map.get(g["ma_mon"], {}).get("ten_mon", g["ma_mon"]),
                    "diem_10": g["diem_10"],
                    "hoc_ky": g["hoc_ky"],
                }
                for g in st.get("bang_diem", [])
                if not g.get("dat", True)
            ]

            if ev.get("scholarship_priority"):
                kkht_status = f"Đủ điều kiện (Mức {ev.get('scholarship_tier')})"
            elif ev.get("scholarship_trap_low_drl"):
                kkht_status = f"Không đủ điều kiện ({ev.get('scholarship_trap_reason')})"
            elif int(st.get("owed_credits", 0)) > 0:
                kkht_status = f"Không đủ điều kiện (Còn nợ {st.get('owed_credits')} tín chỉ)"
            else:
                kkht_status = f"Chưa đạt ngưỡng GPA >= 3.20 (GPA hiện tại: {st['gpa_semester']:.2f})"

            overload_status = (
                "Đủ điều kiện đăng ký học vượt lên 24 tín chỉ (GPA >= 2.50, không nợ môn)"
                if ev.get("overload_eligible")
                else "Chưa đủ điều kiện học vượt (GPA < 2.50 hoặc còn nợ môn / cảnh báo)"
            )
            warning_status = (
                f"Nguy cơ cảnh báo học vụ ({'; '.join(ev.get('warning_reasons', []))})"
                if ev.get("warning_risk")
                else "An toàn (Không thuộc diện cảnh báo học vụ)"
            )

            return {
                "found": True,
                "mssv": st["student_id"],
                "ho_ten": st["full_name"],
                "lop": active_roster.get("class_id"),
                "khoa_tuyen_sinh": active_roster.get("cohort"),
                "nganh": active_roster.get("major"),
                "co_van_hoc_tap": active_roster.get("advisor"),
                "gpa": float(st["gpa_semester"]),
                "drl": int(st["drl"]),
                "tin_chi_tich_luy": int(st["accumulated_credits"]),
                "tin_chi_no": int(st["owed_credits"]),
                "nhom": st.get("nhom"),
                "trang_thai_kkht": kkht_status,
                "trang_thai_hoc_vuot": overload_status,
                "trang_thai_canh_bao": warning_status,
                "mon_no": failed_courses,
            }

    return {"found": False, "mssv": target_id}


def precheck_class_summary(roster: Optional[dict[str, Any]] = None, question: str = "") -> dict[str, Any]:
    """Return deterministic class-level statistics (used only for whole-class queries)."""
    active_roster = roster if roster is not None else load_class_roster()
    analysis = active_roster.get("analysis") or analyze_class_roster(active_roster)
    return {
        "class_id": active_roster.get("class_id"),
        "cohort": active_roster.get("cohort"),
        "major": active_roster.get("major"),
        "advisor": active_roster.get("advisor"),
        "total_students": analysis["total_students"],
        "scholarship_priority_count": analysis["scholarship_priority_count"],
        "scholarship_trapped_count": analysis["scholarship_trapped_count"],
        "overload_eligible_count": analysis["overload_eligible_count"],
        "overload_applicants_count": analysis["overload_applicants_count"],
        "warning_risk_count": analysis["warning_risk_count"],
        "scholarship_priority": [
            {"mssv": s["student_id"], "ho_ten": s["full_name"], "gpa": s["gpa_semester"], "drl": s["drl"], "tier": s.get("scholarship_tier")}
            for s in analysis["scholarship_priority"]
        ],
        "scholarship_trapped_low_drl": [
            {"mssv": s["student_id"], "ho_ten": s["full_name"], "gpa": s["gpa_semester"], "drl": s["drl"], "reason": s.get("scholarship_trap_reason")}
            for s in analysis["scholarship_trapped_low_drl"]
        ],
        "warning_risk": [
            {"mssv": s["student_id"], "ho_ten": s["full_name"], "gpa": s["gpa_semester"], "owed": s["owed_credits"], "reasons": s.get("warning_reasons")}
            for s in analysis["warning_risk"]
        ],
        "overload_applicants": [
            {"mssv": s["student_id"], "ho_ten": s["full_name"], "gpa": s["gpa_semester"], "drl": s["drl"]}
            for s in analysis["overload_applicants"]
        ],
        "top_failed_courses": active_roster.get("top_failed_courses", []),
        "summary_text": format_roster_facts_text(active_roster, question),
    }


def format_single_student_text(sp: dict[str, Any]) -> str:
    """Format strictly one student's profile — guaranteed not to mention any other student."""
    if not sp.get("found"):
        return f"Không tìm thấy sinh viên có mã số {sp.get('mssv')} trong danh sách lớp hiện tại."

    lines = [
        f"Hồ sơ học tập sinh viên {sp['ho_ten']} ({sp['mssv']}) — Lớp {sp['lop']} ({sp['khoa_tuyen_sinh']}) | Cố vấn: {sp['co_van_hoc_tap']}:",
        f"• GPA tích lũy: {sp['gpa']:.2f} | ĐRL (học kỳ 2025.1): {sp['drl']}",
        f"• Tín chỉ tích lũy: {sp['tin_chi_tich_luy']} TC | Tín chỉ nợ: {sp['tin_chi_no']} TC",
        f"• Học bổng KKHT: {sp['trang_thai_kkht']}",
        f"• Học vượt 24 tín chỉ: {sp['trang_thai_hoc_vuot']}",
        f"• Cảnh báo học vụ: {sp['trang_thai_canh_bao']}",
    ]
    mon_no = sp.get("mon_no") or []
    if mon_no:
        no_str = ", ".join(f"{m['ma_mon']} - {m['ten_mon']} ({m['diem_10']})" for m in mon_no)
        lines.append(f"• Học phần chưa đạt (điểm F): {no_str}")
    return "\n".join(lines)


def format_student_detail_text(roster: dict[str, Any], student_id: str) -> Optional[str]:
    """Backward-compatible wrapper around precheck_single_student + format_single_student_text."""
    sp = precheck_single_student(student_id, roster=roster)
    return format_single_student_text(sp) if sp.get("found") else None


def detect_advisor_needs(question: str) -> dict[str, Any]:
    """Detect whether the advisor question requires roster pre-check and/or latest UET news."""
    ql = (question or "").lower()
    student_id_match = _STUDENT_ID_RE.search(ql)
    has_news = any(p in ql for p in _NEWS_PHRASES)

    asks_individual_check = any(
        p in ql
        for p in (
            "bảng điểm",
            "soi điểm",
            "em nào",
            "những em nào",
            "sinh viên nào",
            "10 sinh viên",
            "30 sinh viên",
            "trượt nhiều",
            "tỷ lệ trượt",
            "môn nào",
            "lớp k69",
            "lớp k68",
            "trong lớp có",
            "học vượt",
            "trượt vì",
            "đủ điều kiện",
        )
    ) or bool(student_id_match)

    is_pure_procedure = any(p in ql for p in _PURE_PROCEDURAL_OVERRIDE) and not asks_individual_check
    has_roster = (not is_pure_procedure) and (
        asks_individual_check
        or any(p in ql for p in ("lớp mình", "lớp tôi", "trong lớp"))
        or (has_news and "lớp" in ql)
    )

    return {
        "needs_roster": has_roster,
        "needs_news": has_news,
        "student_id": student_id_match.group(1) if student_id_match else None,
    }


def format_news_facts_text(news_payload: dict[str, Any], roster: Optional[dict[str, Any]] = None) -> str:
    """Format scraped page-1 UET news for prompt grounding and deterministic advisor replies."""
    articles = list(news_payload.get("articles") or [])
    if not articles:
        return "Hiện chưa có bài viết mới nào trong bộ nhớ đệm tin tức UET."

    fetched_at = news_payload.get("fetched_at") or "Vừa cập nhật"
    src = news_payload.get("source") or "cache"
    lines = [
        f"Tin tức / Thông báo mới nhất Trang 1 UET (Nguồn: {src} | Cập nhật: {fetched_at} | {len(articles)} bài):"
    ]
    for idx, art in enumerate(articles, start=1):
        lines.append(
            f"{idx}. [{art.get('category', 'UET')} | {art.get('date', '')}] {art.get('title', '')}"
            f"\n   Tóm tắt: {art.get('summary', '')}"
            f"\n   Liên kết: {art.get('url', '')}"
        )

    if roster is not None:
        analysis = roster.get("analysis") or analyze_class_roster(roster)
        cls_short = roster.get("class_short") or roster.get("class_id")
        p_names = ", ".join(f"{s['full_name']} ({s['gpa_semester']:.2f}/{s['drl']})" for s in analysis["scholarship_priority"])
        w_names = ", ".join(f"{s['full_name']} (GPA {s['gpa_semester']:.2f}, nợ {s['owed_credits']} TC)" for s in analysis["warning_risk"])
        ov_names = ", ".join(f"{s['full_name']}" for s in analysis["overload_applicants"])
        lines.append(f"\nĐối chiếu nhanh với lớp {cls_short} để cố vấn nhắc nhở:")
        if p_names:
            lines.append(f"- Nhắc nộp hồ sơ học bổng KKHT & học bổng doanh nghiệp CNTT (GPA >= 3.2, ĐRL >= 80): {p_names}.")
        if ov_names:
            lines.append(f"- Nhắc theo dõi kế hoạch đăng ký học vượt 24 TC kỳ tới: {ov_names}.")
        if w_names:
            lines.append(f"- Mời làm việc riêng theo thông báo rà soát cảnh báo học vụ: {w_names}.")

    return "\n".join(lines)


def build_deterministic_advisor_answer(
    question: str,
    *,
    roster: Optional[dict[str, Any]] = None,
    news_payload: Optional[dict[str, Any]] = None,
    rag_extractive: str = "",
    mode: str = "chrono_rag",
    student_id: Optional[str] = None,
) -> str:
    """Assemble deterministic fallback answer, strictly respecting single-student scoping."""
    parts: list[str] = []

    if student_id:
        sp = precheck_single_student(student_id, roster=roster)
        parts.append(format_single_student_text(sp))
        # Do NOT append class summary or news containing other students' names when scoped to 1 student
        if mode != "continual_lora" and rag_extractive and "Không tìm thấy thông tin phù hợp" not in rag_extractive:
            clean_rag = re.sub(r"\[[^\]]*\|[^\]]*\]", "", rag_extractive).strip()
            parts.append(f"Căn cứ quy chế UET liên quan:\n{clean_rag}")
        return "\n\n".join(p for p in parts if p).strip()

    if roster is not None:
        parts.append(format_roster_facts_text(roster, question))

    if news_payload is not None:
        parts.append(format_news_facts_text(news_payload, roster=roster))

    ql = (question or "").lower()
    if mode != "continual_lora":
        has_valid_rag = (
            rag_extractive
            and "Không tìm thấy thông tin phù hợp" not in rag_extractive
            and not ("học vượt" in ql and "tuyển sinh" in rag_extractive.lower())
        )
        if has_valid_rag:
            clean_rag = re.sub(r"\[[^\]]*\|[^\]]*\]", "", rag_extractive).strip()
            parts.append(f"Căn cứ quy chế UET liên quan:\n{clean_rag}")
        elif "học vượt" in ql or "24 tín chỉ" in ql:
            parts.append(
                "Căn cứ quy chế đào tạo theo tín chỉ ĐHQGHN/UET:\n"
                "• Sinh viên có học lực từ loại Khá trở lên (GPA/CPA >= 2.50), không nợ học phần và không thuộc diện cảnh báo học tập được phép đăng ký tối đa 24–25 tín chỉ trong một học kỳ chính."
            )
        elif "cảnh báo" in ql:
            parts.append(
                "Quy trình xử lý tiếp theo cho cố vấn học tập:\n"
                "• Cố vấn mời sinh viên thuộc diện cảnh báo học vụ làm việc trực tiếp để lập kế hoạch học lại/cải thiện môn nợ.\n"
                "• Lưu ý đặc biệt với sinh viên đã bị cảnh báo 1 lần: nếu tiếp tục bị cảnh báo lần thứ 2 liên tiếp sẽ thuộc diện xem xét buộc thôi học theo Quy chế đào tạo ĐHQGHN."
            )

    return "\n\n".join(p for p in parts if p).strip()
