"""Answer grounding & abstention verification gates for ChronoReg RAG."""
from __future__ import annotations

import re

from .lexicon import (
    _GROUNDING_GENERIC_WORDS,
    _extract_excluded_phrases,
    _normalize_for_match,
    _normalize_query_typos,
    _tokenize,
)


def _verify_answer_grounding(
    question: str,
    snippet: str,
    bm25_score: float,
    idf_map: dict[str, float],
) -> bool:
    """Return False if the retrieved snippet does not genuinely answer the question (triggers Abstention)."""
    is_small_index = len(idf_map) < 100
    min_bm25 = 0.5 if is_small_index else 12.0
    strong_bm25 = 1.5 if is_small_index else 45.0
    if not snippet or bm25_score < min_bm25:
        return False

    cleaned_q, _ = _extract_excluded_phrases(_normalize_query_typos(question))
    q_clean = cleaned_q.lower()
    s_clean = re.sub(
        r"(?:đại học quốc gia hà nội|trường đại học công nghệ|cộng h[oò]a xã hội chủ nghĩa việt nam|độc lập\s*-\s*tự do\s*-\s*hạnh phúc|hà nội,\s*ngày[^;.\n]*)",
        " ",
        snippet.lower(),
    )

    # 1. Explicit course codes or decision numbers must match in the snippet
    q_course_codes = re.findall(r"\b(?:uet\.)?[a-z]{3}\d{4}\b", q_clean)
    for code in q_course_codes:
        if code not in s_clean:
            return False

    q_dec_codes = re.findall(r"\b(\d{2,5})\s*/\s*(?:qđ|kh|tb|nq)", q_clean)
    for dcode in q_dec_codes:
        if dcode not in s_clean:
            return False

    # 1b. Program total-credit queries must never be answered with a single course line (e.g. 3 TC elective)
    asks_program_total_credits = (
        bool(re.search(r"(?:bao\s+nhiêu|mấy|tổng\s+(?:cộng|số))[^?]{0,20}tín\s+chỉ", q_clean))
        and any(k in q_clean for k in ("ngành ", "chương trình đào tạo", "ctđt"))
        and not any(
            k in q_clean
            for k in ("môn ", "học phần", "học bổng", "kkht", "học phí", "mỗi học kỳ", "học kỳ cuối", "cảnh báo", "tự chọn")
        )
    )
    if asks_program_total_credits:
        has_program_total = (
            "[tổng hợp chương trình đào tạo]" in s_clean
            or "tổng số tín chỉ" in s_clean
            or bool(re.search(r"\b1\d{2}\s*(?:tín\s*chỉ|tc)\b", s_clean))
        )
        if not has_program_total:
            return False

    # 2. Check substantive anchor tokens of the question
    q_uni = _tokenize(q_clean, include_bigrams=False, expand_synonyms=False)
    s_uni_set = set(_tokenize(s_clean, include_bigrams=False, expand_synonyms=True))

    anchor_tokens = [
        t for t in q_uni
        if t not in _GROUNDING_GENERIC_WORDS and not (t.isdigit() and len(t) == 4)
    ]
    if not anchor_tokens:
        has_domain_cue = any(
            k in q_clean
            for k in (
                "học phí", "học bổng", "kkht", "học kỳ", "quy chế", "quy định",
                "quyết định", "tín chỉ", "khóa", "ngành", "nckh", "tuyển sinh", "điểm chuẩn",
            )
        ) or bool(re.search(r"\b(?:tiết|điều|tuần)\s+\d+\b", q_clean))
        if not has_domain_cue:
            return False
        return bm25_score >= (0.5 if is_small_index else 15.0)

    oov_tokens = [t for t in anchor_tokens if t not in idf_map and len(t) >= 2]
    matched_anchors = [t for t in anchor_tokens if t in s_uni_set]

    if not matched_anchors:
        return bm25_score >= strong_bm25
    if not is_small_index and oov_tokens and (len(matched_anchors) / len(anchor_tokens)) < 0.70:
        return False
    if len(anchor_tokens) >= 2 and bm25_score < strong_bm25 and (len(matched_anchors) / len(anchor_tokens)) < 0.30:
        return False

    return True


def verify_llm_grounding(
    question: str,
    llm_answer: str,
    context_text: str,
    bm25_score: float,
    idf_map: dict[str, float],
) -> bool:
    """Post-generation gate for LLM answers: rejects abstention-failure, hallucinated amounts, or ungrounded prose."""
    if not llm_answer or not llm_answer.strip():
        return False

    ans_norm = _normalize_for_match(llm_answer)
    ctx_norm = _normalize_for_match(context_text)

    # Every large currency/numeric figure (>= 5 digits, e.g. 860000, 3200000) stated by the LLM must appear in context
    llm_big_nums = set(re.findall(r"\b\d{5,}\b", ans_norm))
    if llm_big_nums:
        ctx_big_nums = set(re.findall(r"\b\d{5,}\b", ctx_norm))
        if not llm_big_nums.issubset(ctx_big_nums):
            return False

    # Every explicit decision code cited by the LLM must appear in context
    llm_decs = {m.group(1) for m in re.finditer(r"\b(\d{2,5})\s*/\s*(?:qđ|kh|tb|nq)", llm_answer.lower())}
    if llm_decs:
        ctx_low = context_text.lower()
        if any(d not in ctx_low for d in llm_decs):
            return False

    return _verify_answer_grounding(question, llm_answer, bm25_score, idf_map)
