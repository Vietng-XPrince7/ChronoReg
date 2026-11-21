"""Evidence-aware dispatch for a RAG + continual LoRA academic assistant.

A router cannot know factual correctness merely by comparing two fluent outputs.
The default policy protects regulatory answers and allows real LoRA for
non-regulatory explanations/learning advice only, with an explicit label.
Independently evaluated per-bucket metrics may qualify further uses later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

# This is an explicit conservative policy, not a learned accuracy estimate.
_RE_FACT = re.compile(
    r"\b(?:học phí|học bổng|tín chỉ|gpa|điểm số|điều kiện|điều khoản|quy định|"
    r"quy chế|quyết định|nghị định|thông tư|quy trình|thủ tục|"
    r"hồ sơ|nộp ở đâu|nộp khi nào|bao nhiêu|mức thu|thời hạn|"
    r"hạn chót|hiệu lực|được phép|bắt buộc|cần nộp|"
    r"tốt nghiệp|bảo lưu|chuyển ngành|cảnh báo học vụ|"
    r"công nhận|chuẩn đầu ra)\b", re.IGNORECASE)
_RE_TEMPORAL = re.compile(r"\b(?:20(?:2[0-9])|QH-20\d\d|K\d\d|năm nay|hiện hành|mới nhất|"
                          r"học kỳ|khóa|năm học|trước đây|thay thế|so với)\b", re.IGNORECASE)
_RE_ADVICE = re.compile(
    r"(?:cách học|học hiệu quả|cải thiện việc học|lên kế hoạch học|"
    r"ôn thi|ghi nhớ kiến thức|động lực học|quản lý thời gian|"
    r"giải thích khái niệm|giải thích dễ hiểu|cho ví dụ)", re.IGNORECASE)
_RE_GREETING = re.compile(r"^(?:xin chào|chào bạn|hello|hi|hey)[!?\s]*$", re.IGNORECASE)


def classify_question(question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return {"type": "empty", "requires_evidence": True, "allow_lora_advice": False}
    if _RE_GREETING.match(question):
        return {"type": "greeting", "requires_evidence": False, "allow_lora_advice": False}
    # Ambiguous advice with regulatory words is ALWAYS factual first.
    if _RE_FACT.search(question) or _RE_TEMPORAL.search(question):
        return {"type": "regulation", "requires_evidence": True, "allow_lora_advice": False}
    if _RE_ADVICE.search(question):
        return {"type": "general_learning_advice", "requires_evidence": False,
                "allow_lora_advice": True}
    return {"type": "unknown", "requires_evidence": True, "allow_lora_advice": False}


@dataclass(frozen=True)
class Candidate:
    engine: str
    answer: str
    engine_mode: str
    cited_doc_ids: tuple[str, ...] = ()
    # Must be set by a trusted document validator, not by the language model.
    evidence_verified: bool = False
    effective_year_verified: bool = False
    answer_entailment_verified: bool = False
    error: str | None = None
    # Must be set by trusted, independent capability qualification (not the model).
    capability_qualified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"engine": self.engine, "answer": self.answer,
                "engine_mode": self.engine_mode,
                "cited_doc_ids": list(self.cited_doc_ids),
                "evidence_verified": self.evidence_verified,
                "effective_year_verified": self.effective_year_verified,
                "answer_entailment_verified": self.answer_entailment_verified,
                "error": self.error,
                "capability_qualified": self.capability_qualified}


def safe_select(question: str, *, rag: Candidate | None = None,
                lora: Candidate | None = None, is_held: bool = False,
                compare_mode: bool = False) -> dict[str, Any]:
    """Choose a displayed response without inventing confidence or factual accuracy.

    No model-based uncalibrated 'winner'. The strong RAG candidate requires
    independently checked citations and year before factual use.
    """
    kind = classify_question(question)
    result: dict[str, Any] = {"question_type": kind["type"],
        "requires_evidence": kind["requires_evidence"],
        "selected_engine": "abstain", "answer": "",
        "authoritative_regulation_answer": False, "reason": ""}
    if is_held:
        result.update(reason="Publication hold or restricted source: do not automatically answer",
                      answer="Chưa thể xác nhận câu trả lời từ dữ liệu được phép sử dụng.")
        return result
    if kind["type"] == "empty":
        result.update(reason="Empty question", answer="Vui lòng nhập câu hỏi.")
        return result
    if kind["type"] == "greeting":
        result.update(selected_engine="meta", reason="Greeting; no regulatory facts",
                      answer="Xin chào! Tôi có thể hỗ trợ tra cứu quy chế UET theo tài liệu và năm áp dụng.")
        return result

    rag_valid = bool(rag and not rag.error and rag.answer.strip() and
                     rag.cited_doc_ids and rag.evidence_verified and
                     rag.effective_year_verified)
    lora_live = bool(lora and not lora.error and lora.answer.strip() and
                     lora.engine_mode == "LIVE_PEFT_GENERATION")

    if kind["requires_evidence"]:
        if rag_valid:
            result.update(selected_engine="chrono_rag", answer=rag.answer,
                authoritative_regulation_answer=bool(rag.answer_entailment_verified),
                reason=("Citation SHA and year verified; answer entailment checked"
                    if rag.answer_entailment_verified else
                    "Citation SHA and year verified; answer claims NOT independently checked"))
        else:
            result.update(selected_engine="abstain",
                answer="Chưa đủ căn cứ tài liệu và năm áp dụng để xác nhận. Cần tra cứu quy chế gốc.",
                reason="Regulatory question: RAG evidence missing or not verified; LoRA not a factual fallback")
    else:
        # For general non-regulatory learning advice only: no claim of being official UET policy.
        if kind["allow_lora_advice"] and lora_live and lora.capability_qualified:
            result.update(selected_engine="continual_lora", answer=lora.answer,
                          reason="Real LoRA inference, independently qualified for non-regulatory advice; not an official rule")
        elif rag_valid:
            result.update(selected_engine="chrono_rag", answer=rag.answer,
                          reason="LoRA unavailable; documented alternative")
        else:
            result.update(answer="Chưa có câu trả lời được xác minh.",
                          reason="No independently qualified answer engine available; experimental LoRA disabled for auto-selection")

    if compare_mode:
        # Comparison is research-only; predictions are not independent ground truth.
        result["comparison"] = {"rag": rag.to_dict() if rag else None,
                                "lora": lora.to_dict() if lora else None,
                                "winner_validated_by_benchmark": False}
    return result


class HybridDispatch:
    """Dependency-injected bridge; no hidden answer banks or implicit model downloads.

    rag_runner(question) -> Candidate, lora_runner(question) -> Candidate.
    The RAG runner must verify citation SHA/effective year before setting flags.
    """
    def __init__(self, rag_runner: Callable[[str], Candidate] | None = None,
                 lora_runner: Callable[[str], Candidate] | None = None):
        self.rag_runner, self.lora_runner = rag_runner, lora_runner

    def answer(self, question: str, *, compare: bool = False,
               held: bool = False) -> dict[str, Any]:
        kind = classify_question(question)
        if held or kind["type"] in ("empty", "greeting"):
            return safe_select(question, is_held=held, compare_mode=compare)
        rag = None
        lora = None
        if self.rag_runner and (kind["requires_evidence"] or compare):
            try:
                rag = self.rag_runner(question)
            except Exception as exc:
                rag = Candidate("chrono_rag", "", "ERROR", error=str(exc))
        if self.lora_runner and (kind["allow_lora_advice"] or compare):
            try:
                lora = self.lora_runner(question)
            except Exception as exc:
                lora = Candidate("continual_lora", "", "ERROR", error=str(exc))
        return safe_select(question, rag=rag, lora=lora,
                           compare_mode=compare, is_held=held)
