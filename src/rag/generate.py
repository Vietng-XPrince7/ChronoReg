"""Dựng prompt và sinh câu trả lời."""
from __future__ import annotations

from .versioning import VersionPlan


def _header(m: dict) -> str:
    year = m["academic_year"] or "chưa rõ năm học"
    note = "" if m["year_status"] == "verified" else f" [năm học: {m['year_status']}, chưa duyệt]"
    return f"{m['doc_id']} - năm học {year}{note}"


def build_prompt(question: str, hits: list[dict], plan: VersionPlan) -> str:
    ctx = "\n\n".join(f"[{_header(h['metadata'])}]\n{h['document']}" for h in hits)
    if plan.mode in ("year", "latest") and plan.start_year:
        scope = f"Chỉ xét quy định của năm học {plan.label()}."
    else:
        scope = ("Ngữ cảnh có thể gồm nhiều năm học. Nêu rõ từng năm học và "
                 "quy định nào cũ, quy định nào mới.")
    return (
        "Bạn là trợ lý hỏi đáp quy chế của trường đại học. Trả lời bằng tiếng Việt, "
        "chỉ dựa vào các đoạn văn bản dưới đây, nêu rõ văn bản và năm học được trích dẫn. "
        "Nếu đoạn nào ghi 'chưa duyệt' thì nói rõ thông tin chưa được xác minh. "
        "Nếu ngữ cảnh không đủ thì nói rõ là không tìm thấy.\n"
        f"{scope}\n\n=== NGỮ CẢNH ===\n{ctx}\n\n=== CÂU HỎI ===\n{question}"
    )


def generate(question: str, hits: list[dict], plan: VersionPlan, cfg: dict) -> str:
    provider = cfg.get("llm", {}).get("provider", "none")
    if provider == "anthropic":
        import anthropic
        llm = cfg["llm"]
        msg = anthropic.Anthropic().messages.create(
            model=llm["model"],
            max_tokens=llm.get("max_tokens", 800),
            messages=[{"role": "user", "content": build_prompt(question, hits, plan)}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
    # provider "none": trả thẳng các đoạn tìm được để kiểm tra truy xuất/phiên bản
    return "\n\n".join(f"[{_header(h['metadata'])}]\n{h['document'][:600]}" for h in hits[:2])
