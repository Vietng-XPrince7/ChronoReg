"""Dựng prompt và sinh câu trả lời."""
from __future__ import annotations

from .versioning import VersionPlan

OPEN_END = 99991231


def fmt_ts(ts: int) -> str:
    s = str(ts)
    return "nay" if ts == OPEN_END else f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _header(m: dict) -> str:
    return (f"{m['title']} ({m['doc_id']}) - {m['dieu_so']} - "
            f"hiệu lực {fmt_ts(m['effective_ts'])} đến {fmt_ts(m['expired_ts'])}")


def build_prompt(question: str, hits: list[dict], plan: VersionPlan) -> str:
    ctx = "\n\n".join(f"[{_header(h['metadata'])}]\n{h['document']}" for h in hits)
    if plan.mode == "as_of":
        scope = f"Chỉ xét quy định có hiệu lực tại ngày {fmt_ts(plan.t)}."
    elif plan.mode == "current":
        scope = "Chỉ xét quy định đang có hiệu lực hiện nay."
    else:
        scope = ("Ngữ cảnh có thể gồm nhiều phiên bản. Nêu rõ từng phiên bản "
                 "(năm hiệu lực) và quy định nào là cũ, quy định nào là mới.")
    return (
        "Bạn là trợ lý hỏi đáp quy chế của trường đại học. Trả lời bằng tiếng Việt, "
        "chỉ dựa vào các điều khoản dưới đây, nêu rõ Điều và văn bản được trích dẫn. "
        "Nếu ngữ cảnh không đủ thông tin thì nói rõ là không tìm thấy.\n"
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
    # provider "none": trả thẳng các Điều tìm được, để kiểm tra truy xuất/phiên bản
    return "\n\n".join(f"[{_header(h['metadata'])}]\n{h['document']}" for h in hits[:2])
