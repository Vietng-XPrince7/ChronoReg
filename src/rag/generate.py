"""Dựng prompt và SINH câu trả lời từ các đoạn văn bản đã truy xuất.

provider (trong configs/rag.yaml, mục llm):
  none       không dùng LLM: chỉ in lại các đoạn tìm được (để kiểm tra truy xuất)
  local      model chạy trên máy qua transformers (vd Qwen/Qwen2.5-1.5B-Instruct), không cần khóa API
  anthropic  gọi API của Anthropic (cần pip install anthropic và biến môi trường ANTHROPIC_API_KEY)
RAG không cần "huấn luyện": truy xuất đưa đúng đoạn văn bản, LLM đọc rồi tự viết câu trả lời.
"""
from __future__ import annotations

from .versioning import VersionPlan

SYSTEM = (
    "Bạn là trợ lý hỏi đáp quy chế của Trường Đại học Công nghệ (UET, ĐHQGHN). "
    "Trả lời bằng tiếng Việt, ngắn gọn, đúng trọng tâm, bằng lời của bạn (không chép nguyên đoạn văn bản).\n"
    "Quy tắc:\n"
    "1. Chỉ dùng thông tin trong phần NGỮ CẢNH. Không suy đoán, không dùng kiến thức ngoài.\n"
    "2. Số tiền, tỷ lệ, ngày tháng phải giữ nguyên như trong ngữ cảnh.\n"
    "3. Nêu rõ văn bản (hoặc Điều) và năm học mà bạn dựa vào.\n"
    "4. Nếu ngữ cảnh có nhiều năm học khác nhau, nêu từng năm học và chỉ rõ quy định nào áp dụng "
    "cho năm học được hỏi; không lấy mức của năm này để trả lời cho năm khác.\n"
    "5. Đoạn ghi \"(chưa duyệt)\" chưa được xác minh: nếu dùng thì nói rõ.\n"
    "6. Nếu ngữ cảnh không đủ để trả lời, chỉ nói: "
    "\"Không tìm thấy thông tin này trong các văn bản được cung cấp.\""
)


def _header(m: dict) -> str:
    year = f"năm học {m['academic_year']}" if m["academic_year"] else "chưa xác định năm học"
    note = "" if m["year_status"] == "verified" else " (chưa duyệt)"
    dieu = f" - {m['dieu_so']}" if m.get("dieu_so") else ""
    return f"{m['doc_id']}{dieu} - {year}{note}"


def _scope(plan: VersionPlan) -> str:
    if plan.mode == "latest":
        return ("Chỉ xét quy định mới nhất trong dữ liệu"
                + (f" (các năm học: {plan.label()})." if plan.all_years() else "."))
    if plan.mode == "year" and plan.all_years():
        return f"Chỉ xét quy định của năm học {plan.label()}."
    return ("Ngữ cảnh có thể gồm nhiều năm học. Nêu rõ từng năm học và "
            "quy định nào cũ, quy định nào mới.")


def build_user(question: str, hits: list[dict], plan: VersionPlan,
               max_hits: int = 4, max_chars: int = 1200) -> str:
    """Phần người dùng của prompt: phạm vi năm học + ngữ cảnh (cắt ngắn cho model nhỏ) + câu hỏi."""
    ctx = "\n\n".join(
        f"[{i}] {_header(h['metadata'])}\n{h['document'][:max_chars]}"
        for i, h in enumerate(hits[:max_hits], 1)
    )
    return f"{_scope(plan)}\n\n=== NGỮ CẢNH ===\n{ctx}\n\n=== CÂU HỎI ===\n{question}\n\n=== TRẢ LỜI ==="


def build_prompt(question: str, hits: list[dict], plan: VersionPlan) -> str:
    return f"{SYSTEM}\n\n{build_user(question, hits, plan)}"


_local: dict = {}


def _local_chat(system: str, user: str, llm: dict) -> str:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    name = llm["model"]
    if name not in _local:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForCausalLM.from_pretrained(
            name, torch_dtype=torch.float16 if device == "cuda" else torch.float32).to(device).eval()
        _local[name] = (tok, model, device)
    tok, model, device = _local[name]
    text = tok.apply_chat_template(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True)
    inputs = tok(text, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=llm.get("max_new_tokens", 400),
                             do_sample=False, repetition_penalty=1.05)
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def _anthropic_chat(system: str, user: str, llm: dict) -> str:
    import anthropic

    msg = anthropic.Anthropic().messages.create(
        model=llm["model"], max_tokens=llm.get("max_new_tokens", 600), system=system,
        messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def _chat(provider: str, system: str, user: str, llm: dict) -> str:
    if provider == "local":
        return _local_chat(system, user, llm)
    if provider == "anthropic":
        return _anthropic_chat(system, user, llm)
    raise ValueError(f"llm.provider không hợp lệ: {provider!r} (none | local | anthropic)")


def generate(question: str, hits: list[dict], plan: VersionPlan, cfg: dict) -> str:
    llm = cfg.get("llm", {})
    provider = llm.get("provider", "none")
    if provider == "none":
        # không LLM: trả thẳng các đoạn tìm được để kiểm tra truy xuất/phiên bản
        return "\n\n".join(f"[{_header(h['metadata'])}]\n{h['document'][:600]}" for h in hits[:2])
    user = build_user(question, hits, plan, llm.get("max_hits", 4), llm.get("max_context_chars", 1200))
    return _chat(provider, SYSTEM, user, llm)
