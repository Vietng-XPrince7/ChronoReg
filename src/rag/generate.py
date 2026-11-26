"""Dựng prompt và SINH câu trả lời từ các đoạn văn bản đã truy xuất.

provider (trong configs/rag.yaml, mục llm):
  gemini     gọi Google Gemini API (đặt GEMINI_API_KEY trong file .env hoặc biến môi trường; không bắt buộc cài SDK ngoài)
  none       không dùng LLM: chỉ in lại các đoạn tìm được (để kiểm tra truy xuất)
  local      model chạy trên máy qua transformers (vd Qwen/Qwen2.5-1.5B-Instruct), không cần khóa API
  anthropic  gọi API của Anthropic (cần pip install anthropic và biến môi trường ANTHROPIC_API_KEY)
RAG không cần "huấn luyện": truy xuất đưa đúng đoạn văn bản, LLM đọc rồi tự viết câu trả lời.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .versioning import VersionPlan

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_LOADED = False


def load_dotenv_if_present(dotenv_path: Path | None = None) -> None:
    """Load key=value pairs from repo .env into os.environ (handles UTF-8 BOM from PowerShell Set-Content)."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED and dotenv_path is None:
        return
    env_file = dotenv_path or (_REPO_ROOT / ".env")
    if env_file.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False, encoding="utf-8-sig")
        except Exception:
            for raw_line in env_file.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                line = raw_line.strip().lstrip("\ufeff")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lstrip("\ufeff").removeprefix("export ").strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    if dotenv_path is None:
        _DOTENV_LOADED = True


_PLACEHOLDER_KEYS = {
    "your_gemini_api_key_here",
    "dan_api_key_cua_ban_vao_day",
    "dán_api_key_của_bạn_vào_đây",
    "paste_your_api_key_here",
}


def _is_usable_api_key(val: str) -> bool:
    s = val.strip()
    if not s or len(s) < 12:
        return False
    if s.lower() in _PLACEHOLDER_KEYS:
        return False
    # Real API keys are printable ASCII without spaces
    return s.isascii() and not any(ch.isspace() for ch in s)


def resolve_gemini_api_key(llm: dict | None = None) -> str:
    """Resolve Gemini API key from explicit config or environment/.env, ignoring template placeholders."""
    load_dotenv_if_present()
    cfg_llm = llm or {}
    if cfg_llm.get("api_key") and _is_usable_api_key(str(cfg_llm["api_key"])):
        return str(cfg_llm["api_key"]).strip()
    env_name = str(cfg_llm.get("api_key_env") or "GEMINI_API_KEY").strip()
    for candidate in (env_name, "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(candidate, "").strip()
        if _is_usable_api_key(val):
            return val
    return ""


def has_llm_credentials(cfg: dict | None = None) -> bool:
    """Return True if the configured cloud LLM provider has a usable API key."""
    load_dotenv_if_present()
    llm = (cfg or {}).get("llm") or {}
    provider = str(llm.get("provider", "gemini")).lower()
    if provider in ("gemini", "google"):
        return bool(resolve_gemini_api_key(llm))
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    return provider == "local"

SYSTEM = (
    "Bạn là trợ lý hỏi đáp quy chế của Trường Đại học Công nghệ (UET, ĐHQGHN). "
    "Trả lời bằng tiếng Việt, ngắn gọn, đúng trọng tâm, bằng lời của bạn (không chép nguyên đoạn văn bản).\n"
    "Quy tắc:\n"
    "1. Chỉ dùng thông tin trong phần NGỮ CẢNH. Không suy đoán, không dùng kiến thức ngoài.\n"
    "2. Số tiền, điểm chuẩn, số tín chỉ, tỷ lệ, ngày tháng phải giữ nguyên chính xác như trong ngữ cảnh (không tự nhân/chia sinh thêm con số mới).\n"
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
    """Phần người dùng của prompt: phạm vi năm học + ngữ cảnh (phân nhóm theo năm khi đa phiên bản) + câu hỏi."""
    selected = hits[:max_hits]
    distinct_years = list(dict.fromkeys(h["metadata"].get("academic_year") or "" for h in selected))
    if len(distinct_years) > 1 or len(plan.all_years()) > 1:
        year_order = [f"{y}-{y + 1}" for y in plan.all_years()]
        rank = {ay: i for i, ay in enumerate(year_order)}
        ordered = sorted(
            enumerate(selected),
            key=lambda pair: (rank.get(pair[1]["metadata"].get("academic_year") or "", len(rank)), pair[0]),
        )
        blocks: list[str] = []
        last_ay = None
        for idx, (_, h) in enumerate(ordered, 1):
            ay = h["metadata"].get("academic_year") or "chưa rõ năm học"
            if ay != last_ay:
                blocks.append(f"--- NĂM HỌC {ay} ---")
                last_ay = ay
            blocks.append(f"[{idx}] {_header(h['metadata'])}\n{h['document'][:max_chars]}")
        ctx = "\n\n".join(blocks)
    else:
        ctx = "\n\n".join(
            f"[{i}] {_header(h['metadata'])}\n{h['document'][:max_chars]}"
            for i, h in enumerate(selected, 1)
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


def _gemini_chat(system: str, user: str, llm: dict) -> str:
    """Call Google Gemini API via google-genai SDK if installed, else official v1beta REST endpoint."""
    api_key = resolve_gemini_api_key(llm)
    if not api_key:
        raise RuntimeError(
            "Chưa cấu hình GEMINI_API_KEY. Hãy tạo file .env ở thư mục gốc (xem .env.example) "
            "hoặc đặt biến môi trường: $env:GEMINI_API_KEY='...'"
        )
    model_name = (os.environ.get("GEMINI_MODEL", "").strip() or str(llm.get("model") or "gemini-2.5-flash")).strip()
    if model_name.startswith("models/"):
        model_name = model_name.removeprefix("models/")
    max_tokens = int(llm.get("max_new_tokens", 600))
    temperature = float(llm.get("temperature", 0.1))
    timeout_s = float(llm.get("timeout_seconds", 30.0))

    is_pro_thinking = "2.5-pro" in model_name or ("pro" in model_name and "1.5" not in model_name)
    effective_max_tokens = max(max_tokens, 2048) if is_pro_thinking else max_tokens

    # 1. Prefer official google-genai SDK if installed in the environment
    try:
        from google import genai  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]

        client = genai.Client(api_key=api_key)
        cfg_kwargs: dict = {
            "system_instruction": system,
            "temperature": temperature,
            "max_output_tokens": effective_max_tokens,
        }
        if hasattr(types, "ThinkingConfig"):
            if model_name.startswith("gemini-2.5-flash"):
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=int(llm.get("thinking_budget", 0)))
            elif is_pro_thinking:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=int(llm.get("thinking_budget", 512)))
        resp = client.models.generate_content(
            model=model_name,
            contents=user,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )
        return (resp.text or "").strip()
    except ImportError:
        pass

    # 2. Zero-dependency fallback: official Gemini v1beta REST API over HTTPS
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    gen_cfg: dict = {
        "temperature": temperature,
        "maxOutputTokens": effective_max_tokens,
    }
    if model_name.startswith("gemini-2.5-flash"):
        gen_cfg["thinkingConfig"] = {"thinkingBudget": int(llm.get("thinking_budget", 0))}
    elif is_pro_thinking:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": int(llm.get("thinking_budget", 512))}

    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_cfg,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {err_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Không kết nối được Gemini API: {exc.reason}") from exc

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini API không trả về ứng viên nào: {data}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_parts = [str(p.get("text", "")) for p in parts if not p.get("thought") and p.get("text")]
    return "".join(text_parts).strip()


def _chat(provider: str, system: str, user: str, llm: dict) -> str:
    prov = provider.lower().strip()
    if prov in ("gemini", "google"):
        return _gemini_chat(system, user, llm)
    if prov == "local":
        return _local_chat(system, user, llm)
    if prov == "anthropic":
        return _anthropic_chat(system, user, llm)
    raise ValueError(f"llm.provider không hợp lệ: {provider!r} (none | gemini | local | anthropic)")


def generate(question: str, hits: list[dict], plan: VersionPlan, cfg: dict) -> str:
    llm = cfg.get("llm", {})
    provider = llm.get("provider", "none")
    if provider == "none":
        # không LLM: trả thẳng các đoạn tìm được để kiểm tra truy xuất/phiên bản
        return "\n\n".join(f"[{_header(h['metadata'])}]\n{h['document'][:600]}" for h in hits[:2])
    user = build_user(question, hits, plan, llm.get("max_hits", 4), llm.get("max_context_chars", 1200))
    return _chat(provider, SYSTEM, user, llm)
