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
]
_QUANTITATIVE_WORDS = [
    "bao nhiêu tiền", "mức thu", "học phí", "mức học bổng",
    "mấy tín chỉ", "số tín chỉ", "điểm chuẩn", "tỷ lệ",
    "số quyết định", "định mức", "bao nhiêu %",
]
_COMPARISON_WORDS = [
    "khác gì", "thay đổi", "so với", "trước đây", "quy chế cũ",
    "so sánh", "năm trước", "cũ hơn",
]
_EXCEPTION_WORDS = [
    "ngoại lệ", "xin cứu xét", "xin miễn", "cứu xét", "đặc cách",
]

_GREETING_PATTERNS = [
    r"^(xin\s+)?chào(\s+(bạn|bot|cậu|ad|anh|em))?$",
    r"^(hi|hello|hey)(\s+(bot|bạn))?$",
    r".*(bạn|mày|m|bot)\s+(là\s+ai|tên\s+là\s+gì).*",
    r".*(bạn|mày|m|bot)\s+(biết\s+làm\s+gì|làm\s+được\s+gì|có\s+thể\s+làm\s+gì).*",
    r".*(giúp\s+gì\s+được|hỗ\s+trợ\s+gì\s+được)\s+(cho\s+)?(tôi|sinh\s+viên|mình|em).*",
    r".*(giới\s+thiệu\s+(về\s+)?(bản\s+thân|hệ\s+thống|chức\s+năng)).*",
]
_RE_GREETING = [re.compile(p, re.IGNORECASE) for p in _GREETING_PATTERNS]

# Tokenizer: split on whitespace and common Vietnamese punctuation
_RE_TOKEN_SEP = re.compile(r"[\s\.,;:!?()\[\]{}/\\\"']+")

_HEX_RE = re.compile(r"^[0-9a-f]+$")


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
        question tokens.  We deliberately skip the ``scope`` / ``academic_year``
        field-substring approach because those fields are prose and match too broadly.
        """
        matched: set[str] = set()
        # Tokenise the question on whitespace and punctuation (not hyphens, so
        # the user can type a doc_id directly)
        q_tokens = set(t for t in _RE_TOKEN_SEP.split(question_norm) if len(t) >= 4)

        for doc_id in self._reviewed_documents:
            doc_id_norm = _normalise(doc_id)
            # Split on hyphens to get the meaningful slug segments
            slug_parts = doc_id_norm.split("-")
            # Keep only alphabetic (Vietnamese) segments longer than 3 chars;
            # skip pure-hex hash suffixes and year/numeric fragments.
            meaningful = [
                p for p in slug_parts
                if len(p) >= 4 and not p.isdigit() and not _is_hex(p)
            ]
            if any(p in q_tokens for p in meaningful):
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
