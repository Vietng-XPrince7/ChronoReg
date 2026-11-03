"""Đo lường định lượng cho module đánh giá (src/eval/metrics.py).

Không phụ thuộc vào API ngoài (OpenAI/Anthropic). Hoạt động hoàn toàn offline,
tối ưu hóa cho tiếng Việt và các đặc trưng thời gian (temporal/versioning).
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any, Sequence

DISCLAIMER_PHRASES = (
    "cũ",
    "trước đây",
    "trước kia",
    "hết hiệu lực",
    "không còn hiệu lực",
    "đã bị thay thế",
    "bị thay thế",
    "trước khi sửa đổi",
    "lỗi thời",
    "trước đó",
    "thay bằng",
    "thay cho",
)

VIETNAMESE_STOPWORDS = {
    "theo", "quy", "định", "năm", "học", "của", "cho", "trong", "các", "và",
    "là", "được", "với", "tại", "về", "tháng", "tín", "chỉ", "sinh", "viên",
    "khóa", "mức", "mức", "này", "đó", "ra", "vào",
}


def normalize_vietnamese(text: str) -> str:
    """Chuẩn hóa chuỗi văn bản tiếng Việt cho so khớp định lượng:
    - Chuyển unicode dạng chuẩn NFKC, chữ thường
    - Chuẩn hóa các dạng gạch nối/dấu cách năm học (2023 - 2024 -> 2023-2024)
    - Chuẩn hóa tiền tệ (1.850.000đ, 1.850.000 đồng, 1850000 VNĐ -> 1850000)
    - Loại bỏ dấu câu không cần thiết, chuẩn hóa khoảng trắng
    """
    if text is None:
        return ""
    s = str(text)
    if not s:
        return ""

    # Chuẩn hóa Unicode NFKC và chuyển thường
    s = unicodedata.normalize("NFKC", s).casefold()

    # Chuẩn hóa gạch ngang năm học: 2023 - 2024 -> 2023-2024
    s = re.sub(r"(\b20\d{2})\s*[-–—/]\s*(20\d{2}\b)", r"\1-\2", s)

    # Chuẩn hóa số tiền có phân tách nghìn dạng chấm/phẩy: 1.850.000 hoặc 1,850,000 -> 1850000
    def _clean_currency(m: re.Match) -> str:
        val = m.group(0)
        for term in ("đồng", "dong", "vnđ", "vnd", "đ", "d", ".", ",", " "):
            val = val.replace(term, "")
        return val

    s = re.sub(
        r"\b\d{1,3}(?:[.,]\d{3})+(?:\s*(?:đồng|dong|vnđ|vnd|đ|d))?",
        _clean_currency,
        s,
        flags=re.IGNORECASE,
    )

    # Thay thế các ký tự gạch nối khác bằng khoảng trắng nếu không phải khoảng năm
    s = re.sub(r"(?<!20\d{2})[-–—/](?!20\d{2})", " ", s)

    # Giữ lại các ký tự từ (word characters), số, và gạch nối năm
    tokens = re.findall(r"\b20\d{2}-20\d{2}\b|[\w]+", s)
    return " ".join(tokens)


def token_f1(predicted: str, reference: str) -> float:
    """Tính điểm Word-level F1 giữa câu trả lời dự đoán và Ground Truth."""
    p_norm = normalize_vietnamese(predicted)
    r_norm = normalize_vietnamese(reference)
    p_tokens = p_norm.split()
    r_tokens = r_norm.split()

    if not p_tokens or not r_tokens:
        return 1.0 if not p_tokens and not r_tokens else 0.0

    p_counter = Counter(p_tokens)
    r_counter = Counter(r_tokens)
    common = sum((p_counter & r_counter).values())

    if common == 0:
        return 0.0

    precision = common / len(p_tokens)
    recall = common / len(r_tokens)
    f1 = 2 * precision * recall / (precision + recall)
    return float(f1)


def exact_match(predicted: str, reference: str) -> float:
    """So khớp chính xác sau khi đã chuẩn hóa văn bản (1.0 nếu khớp, 0.0 nếu khác)."""
    p_norm = normalize_vietnamese(predicted)
    r_norm = normalize_vietnamese(reference)
    return 1.0 if p_norm == r_norm else 0.0


def key_fact_score(predicted: str, key_facts: Sequence[str] | None) -> float:
    """Tính tỷ lệ các thực thể số, điều khoản, hoặc từ khóa bắt buộc (key_facts) xuất hiện trong câu trả lời.

    Hỗ trợ so khớp linh hoạt:
    - Nếu fact chứa số/mã quyết định/năm: bắt buộc tất cả các số/mã phải có trong câu trả lời,
      kèm tối thiểu 40% các từ mô tả.
    - Nếu fact là cụm từ thuần chữ: khớp chuỗi con hoặc tối thiểu 65% từ khóa thực chất.
    """
    if not key_facts:
        return 1.0
    if not predicted:
        return 0.0

    p_norm = normalize_vietnamese(predicted)
    p_tokens_set = set(p_norm.split())
    matched_count = 0

    for fact in key_facts:
        f_norm = normalize_vietnamese(fact)
        if not f_norm or f_norm in p_norm:
            matched_count += 1
            continue

        f_tokens = f_norm.split()
        if not f_tokens:
            matched_count += 1
            continue

        # Khớp toàn bộ token
        if all(tok in p_tokens_set for tok in f_tokens):
            matched_count += 1
            continue

        f_nums = [tok for tok in f_tokens if any(c.isdigit() for c in tok)]
        f_words = [tok for tok in f_tokens if not any(c.isdigit() for c in tok) and len(tok) > 1 and tok not in VIETNAMESE_STOPWORDS]

        if f_nums:
            # Fact có số: bắt buộc toàn bộ số phải xuất hiện
            if all(num in p_tokens_set for num in f_nums):
                if not f_words or (sum(1 for w in f_words if w in p_tokens_set) / len(f_words) >= 0.4):
                    matched_count += 1
                    continue
        elif len(f_words) >= 2:
            # Fact thuần chữ: kiểm tra độ phủ từ vựng thực chất
            if sum(1 for w in f_words if w in p_tokens_set) / len(f_words) >= 0.65:
                matched_count += 1
                continue

    return matched_count / len(key_facts)


def temporal_accuracy(
    predicted_answer: str,
    gold_doc_id: str | None = None,
    gold_year: int | None = None,
    cited_doc_ids: Sequence[str] | None = None,
    predicted_year: int | None = None,
) -> dict[str, Any]:
    """Đánh giá tính chính xác về mặt thời gian và căn cứ văn bản của câu trả lời.

    Returns:
        {
            "doc_correct": bool,
            "year_correct": bool,
            "score": float  # 1.0 nếu đúng cả hai, 0.5 nếu đúng một, 0.0 nếu sai cả hai
        }
    """
    p_text = predicted_answer or ""
    p_lower = p_text.lower()

    # Kiểm tra doc_id
    doc_correct = True
    if gold_doc_id:
        doc_clean = gold_doc_id.strip().lower()
        cited_clean = [str(c).strip().lower() for c in (cited_doc_ids or [])]
        in_cited = doc_clean in cited_clean or any(doc_clean in c for c in cited_clean)
        in_text = doc_clean in p_lower
        doc_correct = in_cited or in_text

    # Kiểm tra mốc năm
    year_correct = True
    if gold_year is not None:
        y_str = str(gold_year)
        ay_pattern = f"{gold_year}-{gold_year + 1}"
        in_pred_year = (predicted_year == gold_year)
        in_text = (y_str in p_text) or (ay_pattern in p_text)
        year_correct = in_pred_year or in_text

    # Tính điểm tổng hợp
    score = (1.0 if doc_correct and year_correct else
             0.5 if (doc_correct or year_correct) else
             0.0)

    return {
        "doc_correct": doc_correct,
        "year_correct": year_correct,
        "score": score,
    }


def ohr_score(
    predicted: str,
    outdated_trap_answer: str | Sequence[str] | None = None,
    category: str | None = None,
    target_year: int | None = None,
    predicted_year: int | None = None,
) -> float:
    """Outdated Hallucination Rate (OHR / Error Rate):
    Phát hiện xem câu trả lời có vi phạm việc cung cấp thông tin quy chế cũ không còn hiệu lực.

    Một câu trả lời bị tính là vi phạm Outdated Hallucination (OHR = 1.0) nếu:
    (a) Chứa thông tin/số liệu khớp với outdated_trap_answer mà KHÔNG có từ khóa cảnh báo hết hiệu lực, HOẶC
    (b) Câu hỏi thuộc nhóm active_rule (hỏi quy định đang có hiệu lực hiện hành) nhưng hệ thống lại trích xuất
        câu trả lời từ một văn bản đã hết hiệu lực (predicted_year < target_year) mà KHÔNG có cảnh báo.

    Trả về:
        1.0: Nếu vi phạm ảo giác lỗi thời.
        0.0: Nếu câu trả lời sạch, hoặc đã nêu rõ cảnh báo quy định cũ/hết hiệu lực.
    """
    if not predicted:
        return 0.0

    p_norm = normalize_vietnamese(predicted)

    # Nếu câu trả lời có chứa tuyên bố quy định cũ / đã bị thay thế / hết hiệu lực -> Miễn trừ OHR
    if any(d in p_norm for d in DISCLAIMER_PHRASES):
        return 0.0

    # (b) Kiểm tra vi phạm trích xuất văn bản năm cũ cho câu hỏi active_rule
    if category == "active_rule" and target_year is not None and predicted_year is not None:
        if predicted_year < target_year:
            return 1.0

    # (a) Kiểm tra thông tin/số liệu bẫy lỗi thời
    if not outdated_trap_answer:
        return 0.0

    traps = [outdated_trap_answer] if isinstance(outdated_trap_answer, str) else list(outdated_trap_answer)

    for trap in traps:
        if not trap:
            continue
        t_norm = normalize_vietnamese(trap)
        if not t_norm:
            continue

        # 1. Nếu toàn bộ chuỗi bẫy nằm trong câu trả lời
        if t_norm in p_norm:
            return 1.0

        # 2. Nếu bẫy chứa số tiền hoặc định lượng đặc thù (>= 5 chữ số)
        t_numbers = set(re.findall(r"\b\d{5,}\b", t_norm))
        if t_numbers:
            p_numbers = set(re.findall(r"\b\d{5,}\b", p_norm))
            if t_numbers & p_numbers:
                return 1.0
            continue  # Nếu có số mà không trùng số thì không xét tiếp để tránh trùng stopword

        # 3. Nếu bẫy thuần chữ: kiểm tra các từ thực chất không phải stopword
        t_tokens = [tok for tok in t_norm.split() if len(tok) >= 2 and tok not in VIETNAMESE_STOPWORDS]
        if len(t_tokens) >= 3:
            p_tokens_set = set(p_norm.split())
            if sum(1 for tok in t_tokens if tok in p_tokens_set) / len(t_tokens) >= 0.7:
                return 1.0

    return 0.0


def compute_forgetting_matrix(stage_results: dict[int, dict[int, float]]) -> dict[str, Any]:
    """Tính ma trận suy giảm kiến thức (Catastrophic Forgetting Matrix) cho Continual Learning."""
    stages = sorted(stage_results.keys())
    drops: dict[str, dict[str, float]] = {}
    all_drops: list[float] = []

    for stage in stages:
        drops[str(stage)] = {}
        for test_year in sorted(y for y in stage_results[stage] if y < stage):
            prior_scores = [stage_results[s][test_year] for s in stages
                            if test_year <= s < stage and test_year in stage_results[s]]
            if prior_scores:
                drop = max(0.0, max(prior_scores) - stage_results[stage][test_year])
                drops[str(stage)][str(test_year)] = round(drop, 4)
                all_drops.append(drop)

    mean_drop = sum(all_drops) / len(all_drops) if all_drops else 0.0
    return {
        "matrix": {str(s): {str(y): round(sc, 4) for y, sc in m.items()} for s, m in stage_results.items()},
        "forgetting_drops": drops,
        "mean_forgetting": round(mean_drop, 4),
        "backward_transfer": round(-mean_drop, 4),
    }


def latency_stats(timings_ms: Sequence[float]) -> dict[str, float]:
    """Tính toán thống kê độ trễ phản hồi (ms/câu)."""
    if not timings_ms:
        return {
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "p95_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "count": 0,
        }

    sorted_t = sorted(timings_ms)
    n = len(sorted_t)
    mean_val = sum(sorted_t) / n
    median_val = sorted_t[n // 2] if n % 2 != 0 else (sorted_t[n // 2 - 1] + sorted_t[n // 2]) / 2.0
    p95_idx = min(n - 1, math.ceil(0.95 * n) - 1)
    p95_val = sorted_t[p95_idx]

    return {
        "mean_ms": round(mean_val, 2),
        "median_ms": round(median_val, 2),
        "p95_ms": round(p95_val, 2),
        "min_ms": round(sorted_t[0], 2),
        "max_ms": round(sorted_t[-1], 2),
        "count": n,
    }
