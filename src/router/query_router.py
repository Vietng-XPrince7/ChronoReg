"""
query_router.py — AdaptiveQueryRouter for ChronoReg
Routes Vietnamese university regulation questions to the appropriate answer engine.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Static pros/cons dicts
# ---------------------------------------------------------------------------

LORA_PROS_CONS = {
    "pros": "Tổng hợp ngôn ngữ tự nhiên mượt mà; hiểu thuật ngữ nội bộ UET; không cần truy xuất văn bản",
    "cons": "Có thể nhớ sai số liệu định mức (học phí, học bổng) của năm cũ; không có căn cứ văn bản trực tiếp",
}

RAG_PROS_CONS = {
    "pros": "Truy xuất trực tiếp từ văn bản gốc đã xác thực; khóa chính xác theo năm hiệu lực; có SHA-256 truy vết",
    "cons": "Câu trả lời phụ thuộc vào chất lượng chunk; không tổng hợp được câu hỏi mở rộng phức tạp",
}

# ---------------------------------------------------------------------------
# Routing reason strings
# ---------------------------------------------------------------------------

REASON_RED = (
    "Chủ đề chạm văn bản đang khóa Publication Hold hoặc xin ngoại lệ vượt quy chế "
    "→ Chặn tự động trả lời để đảm bảo an toàn pháp lý."
)
REASON_GREETING = (
    "Câu hỏi chào hỏi hoặc tìm hiểu chức năng hệ thống. "
    "Kích hoạt phản hồi giới thiệu trực tiếp cấu trúc năng lực của hệ thống (LoRA 3B, Chrono-RAG 3B, Cổng kiểm duyệt 3 tầng)."
)
REASON_RAG_GREEN = (
    "Câu hỏi yêu cầu số liệu định mức / mốc hiệu lực theo năm học. "
    "Chọn Chrono-RAG 3B để khóa chính xác điều khoản qua Versioning Registry "
    "(tránh rủi ro nhớ nhầm số liệu năm cũ của Continual LoRA)."
)
REASON_RAG_YELLOW = (
    "Câu hỏi liên quan so sánh hoặc giao thoa nhiều phiên bản quy chế. "
    "Chọn Chrono-RAG 3B để tra đúng điều khoản từng năm học "
    "(Continual LoRA có nguy cơ lẫn số liệu giữa các phiên bản)."
)
REASON_LORA = (
    "Câu hỏi thuộc nhóm quy trình & tư vấn học vụ chung. "
    "Chọn Continual LoRA 3B để tận dụng khả năng tổng hợp mượt mà, "
    "hiểu thuật ngữ nội bộ UET từ trọng số đã fine-tune mà không tốn độ trễ truy xuất văn bản."
)

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class RoutingAnalysis:
    selected_engine: str          # "chrono_rag" | "continual_lora" | "safety_gate_red"
    actual_engine_used: str       # same as selected_engine initially
    risk_tier: str                # "GREEN" | "YELLOW" | "RED"
    detected_signals: list[str]   # e.g. ["Mốc năm 2026", "Định mức số liệu"]
    routing_reason: str           # human-readable explanation
    lora_pros_cons: dict          # {"pros": str, "cons": str}
    rag_pros_cons: dict           # {"pros": str, "cons": str}


# ---------------------------------------------------------------------------
# Signal patterns
# ---------------------------------------------------------------------------

# Years 2021-2026 as a simple alternation
_RE_YEAR = re.compile(r"\b(2021|2022|2023|2024|2025|2026)\b")
# Cohort keywords K65-K71 or QH-202x
_RE_COHORT = re.compile(r"\b(K6[5-9]|K7[01]|QH-20\d{2})\b", re.IGNORECASE)

_TEMPORAL_WORDS = [
    "năm nay", "hiện tại", "mới nhất", "hiện hành", "học kỳ", "niên khóa",
    "học kỳ hè", "học kỳ phụ",
]
_QUANTITATIVE_WORDS = [
    "bao nhiêu tiền", "mức thu", "học phí", "mức học bổng", "học bổng kkht",
    "mấy tín chỉ", "số tín chỉ", "tổng tín chỉ", "điểm chuẩn", "tỷ lệ",
    "số quyết định", "định mức", "bao nhiêu %",
    "phòng nào", "mấy giờ", "tiết ", "môn học nào", "học phần nào",
    "điểm rèn luyện", "học vượt", "24 tín chỉ", "bảng điểm",
]
_COMPARISON_WORDS = [
    "khác gì", "thay đổi", "so với", "trước đây", "quy chế cũ",
    "so sánh", "năm trước", "cũ hơn",
]
_EXCEPTION_WORDS = [
    "ngoại lệ", "xin cứu xét", "cứu xét", "đặc cách", "vượt quy chế", "ngoài quy định",
]

_GREETING_PATTERNS = [
    r"^(?:xin\s+)?chào(?:\s+(?:bạn|bot|cậu|ad|anh|em))?[\s!?.]*$",
    r"^(?:hi|hello|hey)(?:\s+(?:bot|bạn))?[\s!?.]*$",
    r"^(?:(?:xin\s+)?chào(?:\s+(?:bạn|bot))?[,!\s]+)?(?:bạn|mày|m|bot)\s+(?:là\s+ai|tên\s+(?:là\s+)?gì)[\s!?.]*$",
    r"^(?:(?:xin\s+)?chào(?:\s+(?:bạn|bot))?[,!\s]+)?(?:bạn|mày|m|bot)\s+(?:biết\s+làm\s+gì|làm\s+được\s+gì|có\s+thể\s+làm\s+gì)[\s!?.]*$",
    r"^(?:(?:bạn|bot)\s+)?(?:giúp\s+gì\s+được|hỗ\s+trợ\s+gì\s+được)(?:\s+cho)?(?:\s+(?:tôi|sinh\s+viên|mình|em))?[\s!?.]*$",
    r"^(?:hãy\s+)?giới\s+thiệu\s+(?:về\s+)?(?:bản\s+thân|hệ\s+thống|chức\s+năng)[\s!?.]*$",
]
_RE_GREETING = [re.compile(p, re.IGNORECASE) for p in _GREETING_PATTERNS]

# Tokenizer: split on whitespace and common Vietnamese punctuation
_RE_TOKEN_SEP = re.compile(r"[\s\.,;:!?()\[\]{}/\\\"']+")

_HEX_RE = re.compile(r"^[0-9a-f]+$")

# Slug tokens that are too generic/common in Vietnamese to be reliable discriminators.
# A doc must match via a NON-stop-word slug token, or via 2+ slug tokens simultaneously.
_SLUG_STOPWORDS: set[str] = {
    "dinh", "khoa", "bieu", "thoi", "nckh", "danh", "sach", "bong",
    "dung", "theo", "dieu", "chinh", "nganh", "hoach", "nghi", "quyet",
    "thuc", "hien", "hanh", "bien", "nhan", "vien", "sinh", "luan",
    "quydinh", "truong", "cong", "nghe", "thong",
}


def _is_hex(s: str) -> bool:
    """Return True if the string looks like a hex hash fragment."""
    return bool(_HEX_RE.match(s)) and len(s) >= 6


def _normalise(text: str) -> str:
    """Lowercase — Vietnamese chars preserved, only ASCII case-folded."""
    return text.lower()


def _contains_any(text: str, phrases: list[str]) -> bool:
    """Return True if the normalised text contains any of the given phrases."""
    for phrase in phrases:
        if phrase in text:
            return True
    return False


# ---------------------------------------------------------------------------
# Main router class
# ---------------------------------------------------------------------------


class AdaptiveQueryRouter:
    """
    Routes a Vietnamese university regulation question to the best answer engine:
    - ``chrono_rag``      – BM25 retrieval from versioned regulation documents
    - ``continual_lora``  – Qwen2.5-3B with per-year LoRA adapters
    - ``safety_gate_red`` – blocked (publication hold / exception request)
    """

    # Default repo root: two levels above this file (src/router/query_router.py → repo root)
    _DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = Path(repo_root) if repo_root is not None else self._DEFAULT_REPO_ROOT
        self._reviewed_documents: dict[str, dict] = {}   # doc_id → record
        self._publication_holds: set[str] = set()         # set of doc_ids on hold
        # doc_ids that appear in same_series approved_relations
        self._multi_version_doc_ids: set[str] = set()

        self._load_data()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_jsonl(self, relative_path: str) -> list[dict]:
        path = self._repo_root / relative_path
        records: list[dict] = []
        if not path.exists():
            return records
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records

    def _load_data(self) -> None:
        # reviewed_documents
        for rec in self._load_jsonl("data/versioning/reviewed_documents.jsonl"):
            doc_id = rec.get("doc_id", "")
            if doc_id:
                self._reviewed_documents[doc_id] = rec

        # publication_holds
        for rec in self._load_jsonl("data/versioning/publication_holds.jsonl"):
            doc_id = rec.get("doc_id", "")
            if doc_id:
                self._publication_holds.add(doc_id)

        # approved_relations — collect doc_ids involved in same_series links
        for rec in self._load_jsonl("data/versioning/approved_relations.jsonl"):
            if rec.get("relation_type") == "same_series":
                from_id = rec.get("from_doc_id", "")
                to_id = rec.get("to_doc_id", "")
                if from_id:
                    self._multi_version_doc_ids.add(from_id)
                if to_id:
                    self._multi_version_doc_ids.add(to_id)

    # ------------------------------------------------------------------
    # Simple doc matching
    # ------------------------------------------------------------------

    def _match_doc_ids(self, question_norm: str) -> set[str]:
        """
        Fuzzy scan: check whether any doc_id slug keyword (meaningful word-tokens)
        from reviewed_documents appears in the normalised question.

        Strategy: split each doc_id on hyphens to get word tokens, ignore very
        short tokens and pure-numeric hash suffixes, then check intersection with
        question tokens.

        Guard against false positives from generic Vietnamese words (e.g. "khoa",
        "dinh", "bong") that appear in many slugs but also in unrelated questions:
        - If the matching token is in _SLUG_STOPWORDS, require at least 2 tokens to
          match simultaneously (not just 1) before marking the doc as matched.
        - Otherwise (the token is a meaningful discriminator), 1 match suffices.
        """
        matched: set[str] = set()
        # Tokenise the question on whitespace and punctuation (not hyphens, so
        # the user can type a doc_id directly)
        q_tokens = set(t for t in _RE_TOKEN_SEP.split(question_norm) if len(t) >= 4)

        for doc_id in self._reviewed_documents:
            doc_id_norm = _normalise(doc_id)
            if doc_id_norm in q_tokens:
                matched.add(doc_id)
                continue
            # Split on hyphens to get the meaningful slug segments
            slug_parts = doc_id_norm.split("-")
            # Keep only alphabetic (Vietnamese) segments longer than 3 chars;
            # skip pure-hex hash suffixes and year/numeric fragments.
            meaningful = [
                p for p in slug_parts
                if len(p) >= 4 and not p.isdigit() and not _is_hex(p)
            ]
            # Tokens in the slug that also appear in the question
            hit_tokens = [p for p in meaningful if p in q_tokens]
            if not hit_tokens:
                continue
            # If ALL matching tokens are stop-words, require >= 2 of them to co-occur
            # (prevents "khoa" in "Khoa học dịch vụ K70" from matching the
            # "uet-thoi-khoa-bieu-hoc-ki-i-2022-2023" timetable doc).
            all_stopwords = all(t in _SLUG_STOPWORDS for t in hit_tokens)
            if all_stopwords and len(hit_tokens) < 2:
                continue
            matched.add(doc_id)

        return matched

    # ------------------------------------------------------------------
    # Signal detection
    # ------------------------------------------------------------------

    def _detect_signals(
        self,
        question: str,
        student_context: dict | None,
    ) -> dict:
        q = _normalise(question)

        has_temporal = bool(
            _RE_YEAR.search(q)
            or _RE_COHORT.search(q)
            or _contains_any(q, _TEMPORAL_WORDS)
        )
        # Check student_context cohort as well
        cohort_from_context: str | None = None
        if student_context:
            cohort = student_context.get("cohort", "")
            if cohort:
                cohort_norm = _normalise(str(cohort))
                cohort_from_context = str(cohort)
                if _RE_COHORT.search(cohort_norm) or _RE_YEAR.search(cohort_norm):
                    has_temporal = True

        has_quantitative = _contains_any(q, _QUANTITATIVE_WORDS)
        has_comparison = _contains_any(q, _COMPARISON_WORDS)

        matched_docs = self._match_doc_ids(q)

        is_exception = _contains_any(q, _EXCEPTION_WORDS) or bool(
            matched_docs & self._publication_holds
        )
        is_multi_version = bool(matched_docs & self._multi_version_doc_ids)
        is_greeting = any(rg.search(q.strip()) for rg in _RE_GREETING)

        # Build detected_signals list
        signals: list[str] = []
        if is_greeting:
            signals.append("Chào hỏi / Hỏi chức năng")
        if has_temporal:
            signals.append("Mốc năm học / Thời gian")
        if has_quantitative:
            signals.append("Định mức số liệu")
        if has_comparison:
            signals.append("So sánh / Lịch sử quy chế")
        if is_exception:
            signals.append("Ngoại lệ / Publication Hold")
        if is_multi_version:
            signals.append("Đa phiên bản quy chế")
        if cohort_from_context and has_temporal:
            signals.append(f"Ngữ cảnh cá nhân (khóa {cohort_from_context})")

        return {
            "has_temporal": has_temporal,
            "has_quantitative": has_quantitative,
            "has_comparison": has_comparison,
            "is_exception": is_exception,
            "is_multi_version": is_multi_version,
            "is_greeting": is_greeting,
            "signals": signals,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route_decision(
        self,
        question: str,
        student_context: dict | None = None,
    ) -> RoutingAnalysis:
        s = self._detect_signals(question, student_context)

        # Priority 0: greeting / meta intent
        if s.get("is_greeting"):
            engine = "meta_greeting"
            tier = "GREEN"
            reason = REASON_GREETING

        # Priority 1: restricted / exception / publication hold
        elif s["is_exception"]:
            engine = "safety_gate_red"
            tier = "RED"
            reason = REASON_RED

        # Priority 2: temporal, quantitative, comparison, or multi-version
        elif (
            s["has_temporal"]
            or s["has_quantitative"]
            or s["has_comparison"]
            or s["is_multi_version"]
        ):
            engine = "chrono_rag"
            if s["has_comparison"] or s["is_multi_version"]:
                tier = "YELLOW"
                reason = REASON_RAG_YELLOW
            else:
                tier = "GREEN"
                reason = REASON_RAG_GREEN

        # Priority 3: general procedural question
        else:
            engine = "continual_lora"
            tier = "GREEN"
            reason = REASON_LORA

        return RoutingAnalysis(
            selected_engine=engine,
            actual_engine_used=engine,
            risk_tier=tier,
            detected_signals=s["signals"],
            routing_reason=reason,
            lora_pros_cons=LORA_PROS_CONS,
            rag_pros_cons=RAG_PROS_CONS,
        )

    def classify_query(
        self,
        question: str,
        *,
        roster: dict | None = None,
        mssv: str | None = None,
    ) -> tuple[str, dict]:
        return classify_query(question, roster=roster, mssv=mssv)

    def build_context(
        self,
        category: str,
        entities: dict,
        *,
        roster: dict | None = None,
        news_payload: dict | None = None,
        regulation_rule: str = "",
    ) -> dict:
        return build_context(
            category,
            entities,
            roster=roster,
            news_payload=news_payload,
            regulation_rule=regulation_rule,
        )


# ---------------------------------------------------------------------------
# Advisor Copilot 6-Category Classifier & Scoped Context Builder
# ---------------------------------------------------------------------------

ADVISOR_CATEGORIES = (
    "STUDENT_STATUS",
    "CLASS_STATS",
    "COURSE_TREND",
    "EVENT_NEWS",
    "ELIGIBILITY_CHECK",
    "REGULATION",
)

_RE_MSSV = re.compile(r"\b(2402\d{4}|2302\d{4})\b")
_RE_COURSE_CODE = re.compile(r"\b([A-Z]{3}\d{4})\b", re.IGNORECASE)

_COURSE_TREND_PHRASES = (
    "kỳ tới môn nào khó",
    "môn nào khó nhất kỳ tới",
    "môn nào khó",
    "dự đoán môn khó",
    "xu hướng môn",
    "xu hướng điểm",
    "xu hướng trượt",
    "dự báo xu hướng",
    "môn nào dễ trượt kỳ tới",
    "dễ bị rớt nhất",
    "các kỳ trước môn nào khó",
    "qua các khóa trước",
    "qua các học kỳ gần đây",
)

_EVENT_NEWS_PHRASES = (
    "sự kiện gì",
    "sự kiện sắp tới",
    "sắp tới có sự kiện",
    "sự kiện và hội thảo",
    "tin tức",
    "thông báo mới",
    "mới có thông báo",
    "thông báo nào",
    "thông báo gì",
    "vừa đăng",
    "cổng thông tin",
    "vừa cào",
    "trang chủ uet",
    "tin mới",
    "trang 1",
    "hội thảo",
)

_CLASS_SCOPE_PHRASES = (
    "lớp mình",
    "lớp tôi",
    "lớp k69",
    "lớp k68",
    "k69-cntt1",
    "k68-cntt1",
    "qh-2024",
    "trong lớp",
    "toàn lớp",
    "cả lớp",
    "của lớp",
    "lớp có",
    "bao nhiêu em",
    "những em nào",
    "em nào",
    "mấy em",
    "có mấy",
    "sĩ số",
    "bảng điểm lớp",
    "soi bảng điểm",
    "30 sinh viên",
    "sinh viên nào",
)

_RULE_ELIGIBILITY_MARKERS = (
    "khóa luận",
    "kltn",
    "tốt nghiệp",
    "học vượt",
    "24 tín chỉ",
    "miễn học phần",
    "chuyển ngành",
    "ra trường",
    "đủ điều kiện",
    "cảnh báo học vụ",
    "nguy cơ cảnh báo",
    "đình chỉ",
    "học bổng",
    "kkht",
    "bẫy đrl",
    "đrl dưới",
)

_CLASS_PURE_STATS_MARKERS = (
    "trượt môn nào nhiều",
    "môn nào bị trượt nhiều",
    "tỷ lệ trượt",
    "gpa trung bình",
    "điểm trung bình toàn lớp",
    "phân bố học lực",
    "thống kê lớp",
    "thống kê gpa",
    "thống kê số lượng",
    "sĩ số lớp",
    "tổng quan",
    "tóm tắt tình hình",
)


def _extract_entities(
    question: str,
    *,
    roster: dict | None = None,
    explicit_mssv: str | None = None,
) -> dict:
    from src.demo.class_roster import load_class_roster

    active_roster = roster if roster is not None else load_class_roster()
    students = active_roster.get("students", [])
    courses = active_roster.get("courses", [])

    q_norm = _normalise(question or "")
    matched_mssv: str | None = None
    matched_name: str | None = None

    # 1. Explicit MSSV from UI click or API parameter
    if explicit_mssv and explicit_mssv.strip():
        target = explicit_mssv.strip()
        for st in students:
            if st.get("student_id") == target or st.get("mssv") == target:
                matched_mssv = target
                matched_name = st.get("full_name") or st.get("ho_ten")
                break
        if matched_mssv is None:
            matched_mssv = target

    # 2. MSSV pattern inside question text
    if matched_mssv is None:
        m_id = _RE_MSSV.search(question or "")
        if m_id:
            matched_mssv = m_id.group(1)
            for st in students:
                if st.get("student_id") == matched_mssv or st.get("mssv") == matched_mssv:
                    matched_name = st.get("full_name") or st.get("ho_ten")
                    break

    # 3. Student full name or unique alias match against active roster
    if matched_mssv is None:
        best_len = 0
        # Precompute unique 2-word given name suffixes
        suffix_counts: dict[str, int] = {}
        for st in students:
            name_low = _normalise(st.get("full_name") or st.get("ho_ten") or "")
            parts = name_low.split()
            if len(parts) >= 3:
                suf = " ".join(parts[-2:])
                suffix_counts[suf] = suffix_counts.get(suf, 0) + 1

        for st in students:
            full = st.get("full_name") or st.get("ho_ten") or ""
            full_low = _normalise(full)
            if full_low and re.search(rf"(?<!\w){re.escape(full_low)}(?!\w)", q_norm):
                if len(full_low) > best_len:
                    best_len = len(full_low)
                    matched_mssv = st.get("student_id") or st.get("mssv")
                    matched_name = full
                continue

            parts = full_low.split()
            if len(parts) >= 3:
                suf = " ".join(parts[-2:])
                if suffix_counts.get(suf, 0) == 1 and re.search(rf"(?<!\w){re.escape(suf)}(?!\w)", q_norm):
                    if len(suf) > best_len:
                        best_len = len(suf)
                        matched_mssv = st.get("student_id") or st.get("mssv")
                        matched_name = full
                # Also match "Sơn Tùng" prefix if unique (e.g. "Sơn Tùng MTP")
                pref = " ".join(parts[:2])
                if len(pref) >= 6 and pref not in ("nguyễn văn", "trần văn", "phạm thị") and re.search(rf"(?<!\w){re.escape(pref)}(?!\w)", q_norm):
                    if len(pref) > best_len:
                        best_len = len(pref)
                        matched_mssv = st.get("student_id") or st.get("mssv")
                        matched_name = full

    # 4. Course code / course name extraction
    matched_ma_mon: str | None = None
    matched_ten_mon: str | None = None
    m_code = _RE_COURSE_CODE.search(question or "")
    if m_code:
        cand_code = m_code.group(1).upper()
        for c in courses:
            if c.get("ma_mon", "").upper() == cand_code:
                matched_ma_mon = c["ma_mon"]
                matched_ten_mon = c["ten_mon"]
                break
        if matched_ma_mon is None:
            matched_ma_mon = cand_code

    if matched_ma_mon is None:
        best_c_len = 0
        for c in courses:
            cname = _normalise(c.get("ten_mon", ""))
            if len(cname) >= 5 and re.search(rf"(?<!\w){re.escape(cname)}(?!\w)", q_norm):
                if len(cname) > best_c_len:
                    best_c_len = len(cname)
                    matched_ma_mon = c["ma_mon"]
                    matched_ten_mon = c["ten_mon"]

    # Optional rule topic hint for ELIGIBILITY_CHECK
    rule_topic: str | None = None
    for marker in _RULE_ELIGIBILITY_MARKERS:
        if marker in q_norm:
            rule_topic = marker
            break

    return {
        "mssv": matched_mssv,
        "ho_ten": matched_name,
        "ma_mon": matched_ma_mon,
        "ten_mon": matched_ten_mon,
        "rule_topic": rule_topic,
    }


def classify_query(
    question: str,
    *,
    roster: dict | None = None,
    mssv: str | None = None,
) -> tuple[str, dict]:
    """Classify an advisor question into one of 6 categories and extract scoped entities."""
    entities = _extract_entities(question, roster=roster, explicit_mssv=mssv)
    q_norm = _normalise(question or "")

    # 1. STUDENT_STATUS: tied to a specific student by MSSV or name
    if entities.get("mssv"):
        return "STUDENT_STATUS", entities

    # 2. COURSE_TREND: forecasting / multi-term course difficulty trend
    if (
        _contains_any(q_norm, list(_COURSE_TREND_PHRASES))
        or (("kỳ tới" in q_norm or "học kỳ tới" in q_norm) and "môn" in q_norm and "khó" in q_norm)
        or (
            ("xu hướng" in q_norm or "dự đoán" in q_norm or "dự báo" in q_norm)
            and (entities.get("ma_mon") is not None or any(k in q_norm for k in ("môn", "qua môn", "trượt", "rớt", "điểm", "khó")))
        )
    ):
        return "COURSE_TREND", entities

    # 3. EVENT_NEWS: latest campus events / UET page-1 notices
    has_class_scope = _contains_any(q_norm, list(_CLASS_SCOPE_PHRASES)) or (
        bool(re.search(r"\blớp\b", q_norm)) and "lớp học phần" not in q_norm
    )
    if _contains_any(q_norm, list(_EVENT_NEWS_PHRASES)):
        return "EVENT_NEWS", entities

    # 4 & 5. Class-scoped queries: distinguish CLASS_STATS vs ELIGIBILITY_CHECK
    if has_class_scope:
        if _contains_any(q_norm, list(_CLASS_PURE_STATS_MARKERS)):
            return "CLASS_STATS", entities
        if _contains_any(q_norm, list(_RULE_ELIGIBILITY_MARKERS)):
            return "ELIGIBILITY_CHECK", entities
        return "CLASS_STATS", entities

    # 6. Default: REGULATION (policy, tuition, procedures, exceptions)
    return "REGULATION", entities


def build_context(
    category: str,
    entities: dict,
    *,
    roster: dict | None = None,
    news_payload: dict | None = None,
    regulation_rule: str = "",
) -> dict:
    """Build strictly scoped JSON context for the classified category without leaking full roster."""
    from src.api.advisor_service import (
        format_news_facts_text,
        format_single_student_text,
        precheck_class_summary,
        precheck_single_student,
    )
    from src.demo.class_roster import load_class_roster
    from src.scraper.uet_latest import UETLatestNewsScraper

    active_roster = roster if roster is not None else load_class_roster()

    if category == "STUDENT_STATUS":
        mssv = (entities or {}).get("mssv") or ""
        student_data = precheck_single_student(mssv, roster=active_roster)
        return {
            "category": "STUDENT_STATUS",
            "entities": entities,
            "use_rag": False,
            "use_lora": False,
            "data": student_data,
            "context_text": format_single_student_text(student_data),
        }

    if category == "CLASS_STATS":
        summary = precheck_class_summary(active_roster)
        return {
            "category": "CLASS_STATS",
            "entities": entities,
            "use_rag": False,
            "use_lora": False,
            "data": {k: v for k, v in summary.items() if k != "summary_text"},
            "context_text": summary["summary_text"],
        }

    if category == "COURSE_TREND":
        # Current database covers only a single cohort (K69) without multi-year historical grade trends per course.
        data = {
            "sufficient_historical_data": False,
            "historical_cohorts_available": 1,
            "requested_course": (entities or {}).get("ma_mon"),
            "message": (
                "Chưa đủ dữ liệu bảng điểm lịch sử qua nhiều khóa/nhiều kỳ để dự đoán xu hướng độ khó môn học cho kỳ tới. "
                "Hệ thống không tự suy diễn môn khó khi thiếu dữ liệu thống kê lịch sử."
            ),
        }
        return {
            "category": "COURSE_TREND",
            "entities": entities,
            "use_rag": False,
            "use_lora": False,
            "data": data,
            "context_text": data["message"],
        }

    if category == "EVENT_NEWS":
        news = news_payload if news_payload is not None else UETLatestNewsScraper().get_latest_or_cached(limit=10)
        return {
            "category": "EVENT_NEWS",
            "entities": entities,
            "use_rag": True,
            "use_lora": False,
            "data": {
                "fetched_at": news.get("fetched_at"),
                "source": news.get("source"),
                "articles": news.get("articles", []),
            },
            "context_text": format_news_facts_text(news, roster=None),
        }

    if category == "ELIGIBILITY_CHECK":
        summary = precheck_class_summary(active_roster)
        return {
            "category": "ELIGIBILITY_CHECK",
            "entities": entities,
            "use_rag": True,
            "use_lora": False,
            "data": {
                "step1_regulation_rule": regulation_rule,
                "step2_class_summary": {k: v for k, v in summary.items() if k != "summary_text"},
            },
            "context_text": summary["summary_text"],
        }

    # REGULATION (no roster attached)
    return {
        "category": "REGULATION",
        "entities": entities,
        "use_rag": True,
        "use_lora": True,
        "data": {},
        "context_text": "",
    }
