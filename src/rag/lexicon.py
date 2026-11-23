"""Lexicon loader and Vietnamese text normalization/tokenization for ChronoReg RAG."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

_DEFAULT_LEXICON_PATH = Path(__file__).resolve().parents[2] / "configs" / "rag_lexicon.yaml"

_FALLBACK_TOPIC_MAP: dict[str, str] = {
    "hoc_phi": "tuition",
    "hoc_bong": "scholarship",
    "nckh": "research",
    "dao_tao": "training_rules",
    "ke_hoach": "academic_calendar",
    "tuyen_sinh": "admissions",
    "cong_tac_sinh_vien": "scholarship",
}

_FALLBACK_TYPO_MAP: dict[str, str] = {
    "đạo tạo": "đào tạo",
    "nghành": "ngành",
    "học kì": "học kỳ",
    "kì thi": "kỳ thi",
    "cở sở": "cơ sở",
}

_FALLBACK_STOPWORDS: set[str] = {
    "theo", "quy", "định", "của", "cho", "trong", "các",
    "và", "là", "được", "với", "tại", "về", "này", "đó", "ra", "vào",
    "như", "thế", "nào", "bao", "nhiêu", "trường", "đại", "công", "nghệ",
    "uet", "việc", "những", "khi", "nếu", "thì", "có", "ở", "từ", "đến",
}

_FALLBACK_SYNONYMS: dict[str, list[str]] = {
    "tối_thiểu": ["ít", "nhất", "ít_nhất"],
    "tối_đa": ["nhiều", "nhất", "không_quá"],
    "hiện_nay": ["hiện_hành", "mới_nhất"],
    "còn_lại": ["khác", "chuẩn", "kỹ_thuật"],
    "kỹ_thuật": ["còn_lại", "khác", "chuẩn"],
    "nghiên_cứu": ["tiến_sĩ", "ncs"],
    "tiến_sĩ": ["nghiên_cứu", "nghiên_cứu_sinh", "ncs"],
    "cao_học": ["thạc_sĩ", "hv"],
    "bãi_bỏ": ["thay_thế", "áp_dụng", "hủy_bỏ"],
    "đồng_thời": ["cùng_lúc", "quyền_nhận"],
    "khóa_luận": ["kltn", "đatn"],
}

_FALLBACK_GENERAL_COURSES: tuple[str, ...] = (
    "triết học", "kinh tế chính trị", "chủ nghĩa xã hội", "lịch sử đảng",
    "tư tưởng hồ chí minh", "nhà nước và pháp luật", "tiếng anh", "ngoại ngữ",
    "giáo dục thể chất", "giáo dục quốc phòng", "kỹ năng bổ trợ", "nhập môn công nghệ số",
    "đại số", "giải tích 1", "giải tích 2", "vật lý đại cương",
)

_FALLBACK_VI_ASCII_TAIL: set[str] = {
    "minh", "anh", "nam", "trung", "hoa", "phap", "duc", "nhat", "han", "nga", "la", "ma",
}

_FALLBACK_GENERIC_INTENT: set[str] = {
    "chương", "trình", "đào", "tạo", "chương_trình", "đào_tạo", "ngành", "các",
    "tín", "chỉ", "tín_chỉ", "sinh", "viên", "sinh_viên", "học", "kỳ", "học_kỳ",
    "năm", "mức", "bao", "nhiêu", "gồm", "mấy", "quy", "định", "quy_định", "trường",
    "đại", "công", "nghệ", "hiện", "nay", "hiện_nay", "chuẩn", "hệ", "khóa", "khoá",
    "đóng", "nộp", "tiền", "đồng", "tháng", "thu", "phí", "học_phí", "xét", "cấp",
    "bậc", "của", "cho", "trong", "với", "tại", "về", "như", "thế", "nào", "những",
    "môn", "môn_học", "học_phần", "phần", "làm", "gì", "đâu", "ai", "khi",
    "được", "không", "có", "là", "và", "hoặc", "theo", "từ", "đến", "trước", "sau",
    "em", "mình", "hỏi", "ạ", "vậy", "thì", "phải", "cần", "muốn", "biết",
    "bổng", "học_bổng", "khuyến", "khích", "khuyến_khích", "tập", "học_tập", "kkht",
}

_FALLBACK_GROUNDING_EXTRA: set[str] = {
    "nhất", "lớn", "nhỏ", "bằng", "lần", "đầu", "loại", "mỗi", "toàn", "khoảng",
    "đợt", "ngày", "tháng", "tuần", "tiết", "lúc", "bắt", "kết", "thúc", "thời",
    "học_bổng", "học_kỳ", "năm_học", "văn_bản", "thông_tin", "quy_chế", "hiện_hành",
    "mới_nhất", "trước_đây", "thay_đổi", "so_với", "áp_dụng", "đối_với", "hết",
    "hiệu", "lực", "ngoài", "trừ", "còn", "lại", "khác", "bài", "nếu",
    "trường", "đhqghn", "vnu", "uet", "bậc", "người", "như", "vậy", "đều",
    "lưu", "ý", "mức", "thu", "đóng", "nộp", "xét", "cấp", "thế", "ra", "sao",
    "thời_gian", "quyết_định", "thông_báo", "kế_hoạch", "hướng", "dẫn", "trình", "bày",
    "những", "gì", "cách", "thức", "hình", "việc", "chính", "cụ", "thể",
    "kèm", "theo", "ban", "hành", "hôm", "nay", "thời_điểm", "hiện_tại", "đang",
    "kế", "hoạch", "tập", "bảng", "phụ", "lục", "tổng", "nhóm", "thuộc", "đã", "bị",
    "nhận", "một", "hai", "ba", "bốn", "quyết", "định", "phân", "chia",
}


def load_lexicon(path: Path | str | None = None) -> dict[str, Any]:
    """Load lexicon configuration from configs/rag_lexicon.yaml, falling back gracefully."""
    p = Path(path) if path else _DEFAULT_LEXICON_PATH
    if p.is_file():
        try:
            import yaml
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


_LEX = load_lexicon()

TOPIC_MAP: dict[str, str] = dict(_LEX.get("topic_map") or _FALLBACK_TOPIC_MAP)
_TYPO_MAP: dict[str, str] = dict(_LEX.get("typo_map") or _FALLBACK_TYPO_MAP)
_STOPWORDS: set[str] = set(_LEX.get("stopwords") or _FALLBACK_STOPWORDS)
_QUERY_SYNONYMS: dict[str, list[str]] = {
    str(k): list(v) for k, v in (_LEX.get("query_synonyms") or _FALLBACK_SYNONYMS).items()
}
_GENERAL_COURSE_NAMES: tuple[str, ...] = tuple(_LEX.get("general_course_names") or _FALLBACK_GENERAL_COURSES)
_VI_ASCII_TAIL_WORDS: set[str] = set(_LEX.get("vi_ascii_tail_words") or _FALLBACK_VI_ASCII_TAIL)
_GENERIC_INTENT_WORDS: set[str] = set(_LEX.get("generic_intent_words") or _FALLBACK_GENERIC_INTENT)
_GROUNDING_GENERIC_WORDS: set[str] = _GENERIC_INTENT_WORDS | set(
    _LEX.get("grounding_extra_words") or _FALLBACK_GROUNDING_EXTRA
)

_GENERAL_COURSE_CODE_RE = re.compile(
    r"^(?:UET\.)?(?:POL|PHI|PEC|HIS|LAW|FLF|ENG|PES|GDQP|MIL|VNU|SKD|THL|PSY|SOC|MAT1|PHY1|EPN10)\d*\b",
    re.IGNORECASE,
)
_EXCLUSION_RE = re.compile(
    r"\(\s*(?:ngoài|trừ|không\s+bao\s+gồm|không\s+tính)\s+"
    r"((?:các\s+)?(?:ngành|chương\s+trình)?[^)]*(?:nông\s+nghiệp|hàng\s+không|giao\s+thông|xây\s+dựng|sinh\s+học)[^)]*)\)",
    re.IGNORECASE,
)
_DECISION_CODE_RE = re.compile(
    r"\b(\d{1,5})\s*/\s*(QĐ|KH|TB|NQ|TT|NĐ|CV)\s*[-–]\s*([A-ZĐa-zđ0-9]+)",
    re.IGNORECASE,
)


def _normalize_query_typos(question: str) -> str:
    """Fix common Vietnamese typing errors and normalize Unicode to NFC."""
    q = unicodedata.normalize("NFC", question)
    for wrong, right in _TYPO_MAP.items():
        q = re.sub(wrong, right, q, flags=re.IGNORECASE)
    return q


def _norm_course_name(name: str) -> str:
    """Normalize a Vietnamese course title for exact/fuzzy catalog matching."""
    s = unicodedata.normalize("NFC", name).lower()
    s = re.sub(r"\([^)]*(?:môn\s+tự\s+chọn|tự\s+chọn|bắt\s+buộc|\*|ai|tuần|học)[^)]*\)", " ", s)
    s = re.sub(r"\(\s*\*\s*\)", " ", s)
    s = re.sub(
        r"[^a-zđáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ0-9]+",
        " ",
        s,
    )
    return re.sub(r"\s+", " ", s).strip()


def _normalize_for_match(text: str) -> str:
    """Normalize text and currency numbers to align with src/eval/metrics.py."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).lower()
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\b(\d{1,3})(?:[.,](\d{3}))+\b", lambda m: re.sub(r"[.,]", "", m.group(0)), s)
    s = re.sub(r"\b(\d+),(\d+)\b", r"\1.\2", s)
    s = re.sub(r"(\d+)\s*(?:đồng|vnđ|vnd|đ)\b", r"\1", s)
    s = re.sub(r"\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b", r"\1-\2", s)
    return s


def _extract_excluded_phrases(question: str) -> tuple[str, list[str]]:
    """Strip negative major exclusions like '(ngoài Nông nghiệp và Hàng không)' from question."""
    excluded_tokens: list[str] = []

    def _collect(m: re.Match[str]) -> str:
        phrase = (m.group(1) or "").strip()
        if phrase:
            norm_p = _normalize_for_match(phrase)
            toks = [w for w in re.findall(r"\w+", norm_p) if len(w) > 2 and w not in _STOPWORDS]
            excluded_tokens.extend(toks)
            for i in range(len(toks) - 1):
                excluded_tokens.append(f"{toks[i]}_{toks[i + 1]}")
        return " "

    cleaned_q = _EXCLUSION_RE.sub(_collect, question)
    return cleaned_q, list(dict.fromkeys(excluded_tokens))


def _tokenize(text: str, include_bigrams: bool = True, expand_synonyms: bool = False) -> list[str]:
    """Tokenize normalized Vietnamese text while preserving numbers and compound bigrams."""
    norm = _normalize_for_match(text)
    base_tokens = [
        w for w in re.findall(r"\d+(?:\.\d+)?|\w+", norm)
        if (len(w) > 1 or w.isdigit()) and w not in _STOPWORDS
    ]
    if not include_bigrams:
        return base_tokens

    bigrams = [
        f"{base_tokens[i]}_{base_tokens[i + 1]}"
        for i in range(len(base_tokens) - 1)
        if not (base_tokens[i].isdigit() and base_tokens[i + 1].isdigit() and len(base_tokens[i]) >= 4)
    ]
    all_toks = base_tokens + bigrams
    if expand_synonyms:
        extra: list[str] = []
        for t in all_toks:
            if t in _QUERY_SYNONYMS:
                extra.extend(_QUERY_SYNONYMS[t])
        all_toks.extend(extra)
    return all_toks
