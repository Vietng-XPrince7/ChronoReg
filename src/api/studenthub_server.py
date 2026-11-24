# studenthub_server.py — ChronoReg StudentHub FastAPI server
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Literal
import time, json, re
from pathlib import Path
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from src.lora.web_runtime import web_lora

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = REPO_ROOT / "studenthub_ui"
DATA_DIR = REPO_ROOT / "data" / "versioning"
EVAL_DIR = REPO_ROOT / "runs" / "eval"

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(web_lora.preload)
    yield


app = FastAPI(title="StudentHub — ChronoReg API", lifespan=lifespan)


@app.get("/api/lora/status")
def lora_status():
    return web_lora.status()

# Mount static files for the UI
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


@app.get("/")
def root():
    idx = UI_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return {"message": "StudentHub API running. UI not found."}


# ---------------------------------------------------------------------------
# RAG engine — load once at module level
# ---------------------------------------------------------------------------
_retriever = None
_adapter = None

try:
    from src.rag.eval_adapter import InMemoryRetriever, RAGEvalAdapter
    _retriever = InMemoryRetriever.from_corpus()
    _adapter = RAGEvalAdapter(_retriever)
except Exception as _e:
    import sys
    print(f"[studenthub_server] WARNING: RAG engine failed to load: {_e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Router — load once; fall back to stub if not ready
# ---------------------------------------------------------------------------
_router = None

try:
    from src.router.query_router import AdaptiveQueryRouter, RoutingAnalysis
    _router = AdaptiveQueryRouter(repo_root=REPO_ROOT)
except ImportError as _ie:
    import sys
    print(f"[studenthub_server] WARNING: Router not available, using stub: {_ie}", file=sys.stderr)

    from dataclasses import dataclass, field

    @dataclass
    class RoutingAnalysis:  # type: ignore[no-redef]
        selected_engine: str = "chrono_rag"
        actual_engine_used: str = "chrono_rag"
        risk_tier: str = "GREEN"
        detected_signals: list = field(default_factory=list)
        routing_reason: str = "Stub router — always routes to chrono_rag."
        lora_pros_cons: dict = field(default_factory=lambda: {"pros": "N/A", "cons": "N/A"})
        rag_pros_cons: dict = field(default_factory=lambda: {"pros": "N/A", "cons": "N/A"})

    class _StubRouter:
        def route_decision(self, question: str, student_context=None) -> RoutingAnalysis:
            return RoutingAnalysis()

    _router = _StubRouter()

# ---------------------------------------------------------------------------
# Versioning metadata — load into dicts
# ---------------------------------------------------------------------------
_reviewed_docs: dict = {}   # doc_id -> record dict
_approved_relations: list = []  # list of relation dicts

try:
    with open(DATA_DIR / "reviewed_documents.jsonl", encoding="utf-8") as _fh:
        for _line in _fh:
            _line = _line.strip()
            if _line:
                _rec = json.loads(_line)
                _reviewed_docs[_rec["doc_id"]] = _rec
except Exception as _e:
    import sys
    print(f"[studenthub_server] WARNING: reviewed_documents load failed: {_e}", file=sys.stderr)

try:
    with open(DATA_DIR / "approved_relations.jsonl", encoding="utf-8") as _fh:
        for _line in _fh:
            _line = _line.strip()
            if _line:
                _approved_relations.append(json.loads(_line))
except Exception as _e:
    import sys
    print(f"[studenthub_server] WARNING: approved_relations load failed: {_e}", file=sys.stderr)

# Build a set of doc_ids that appear in a same_series chain (have a newer version)
_superseded_doc_ids: set = set()
for _rel in _approved_relations:
    if _rel.get("relation_type") == "same_series":
        _superseded_doc_ids.add(_rel.get("to_doc_id", ""))

# ---------------------------------------------------------------------------
# Continual LoRA V3 — the shared runtime is preloaded by FastAPI lifespan.
# ---------------------------------------------------------------------------
def _run_web_lora(question: str) -> dict:
    try:
        result = web_lora.generate(question, as_of_year=2026)
        return {
            "predicted_answer": "[Kết quả LoRA thực nghiệm, chưa được xác nhận là quy chế chính thức]\n" + result["answer"],
            "latency_ms": result["latency_ms"],
            "source_label": "QLoRA V3 thực nghiệm (trọng số thật, không trích dẫn tài liệu)",
            "engine_mode": result["engine_mode"],
            "checkpoint_year": result["checkpoint_year"],
            "cited_doc_ids": [],
        }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("LoRA generation unavailable: %s", exc)
        return {
            "predicted_answer": "LoRA V3 chưa sẵn sàng hoặc không sinh được câu trả lời. Kiểm tra trạng thái tại /api/lora/status và log server.",
            "latency_ms": 0.0, "source_label": "LoRA không khả dụng — không có suy luận từ trọng số",
            "engine_mode": "LORA_UNAVAILABLE", "checkpoint_year": None,
            "cited_doc_ids": [],
        }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_HIGHLIGHT_RE = re.compile(
    r"\b(\d[\d.,]*\s*(?:đồng|triệu\s*đồng|nghìn\s*đồng|%|tín chỉ|VNĐ|vnđ)|\bGPA\s*[:=]?\s*\d[.,]\d{1,2}\b|\b\d[.,]\d{1,2}\s*/\s*4\.0\b|\b\d{4}[-/]\d{4}\b|\b(?:QĐ|Quyết\s*định)[-\s]?\d+[\w/-]*\b|\bQH-\d{4}\b|\bK\d{2}\b)",
    re.IGNORECASE,
)


def _highlight(text: str) -> str:
    return _HIGHLIGHT_RE.sub(r"<mark>\1</mark>", text)


def _truncate(text: str, limit: int = 800) -> str:
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _build_metadata(
    cited_doc_ids: list,
    latency_ms: float,
    engine_note: Optional[str] = None,
    actual_engine: str = "chrono_rag",
    pred: Optional[dict] = None,
) -> dict:
    """Build the metadata block for a response, ensuring separation between LoRA & RAG."""
    # Continual LoRA relies on parametric weights, not retrieved documents
    if actual_engine == "continual_lora":
        p = pred or {}
        return {
            "doc_id": None,
            "doc_title": None,
            "effective_year": p.get("checkpoint_year", 2026),
            "sha256_short": None,
            "superseded_warning": None,
            "source_type": "lora_parametric" if p.get("engine_mode") == "LIVE_PEFT_GENERATION" else "lora_unavailable",
            "source_label": p.get("source_label", "LoRA không khả dụng"),
            "engine_mode": p.get("engine_mode", "LORA_UNAVAILABLE"),
            "quality_qualified": False,
            "benchmark_id": p.get("benchmark_id"),
            "token_f1_proxy": p.get("token_f1_proxy"),
            "latency_ms": round(latency_ms, 2),
            "engine_note": engine_note,
        }

    # Chrono-RAG & Naive RAG: document citations and SHA-256 integrity locks
    doc_id = cited_doc_ids[0] if cited_doc_ids else None
    doc_rec = _reviewed_docs.get(doc_id, {}) if doc_id else {}

    sha256 = doc_rec.get("content_sha256", "")
    sha256_short = sha256[:8] if sha256 else None

    # Superseded warning
    superseded_warning = None
    if doc_id and doc_id in _superseded_doc_ids:
        superseded_warning = (
            "Văn bản này có phiên bản mới hơn trong chuỗi quy định, hãy lưu ý năm học áp dụng."
        )

    evidence = doc_rec.get("evidence_reference", "")
    scope = doc_rec.get("scope", "")
    doc_title = None
    if evidence:
        doc_title = evidence.split(";")[0].strip()
    elif scope:
        doc_title = scope[:120]

    effective_year_raw = doc_rec.get("academic_year", "")
    effective_year = None
    if effective_year_raw:
        m = re.search(r"(\d{4})", effective_year_raw)
        if m:
            effective_year = int(m.group(1))

    source_label = f"Căn cứ pháp lý: {doc_title or doc_id or 'Quy định UET'} | Năm: {effective_year or 'N/A'} | SHA-256: {sha256_short or 'N/A'}"

    return {
        "doc_id": doc_id,
        "doc_title": doc_title,
        "effective_year": effective_year,
        "sha256_short": sha256_short,
        "superseded_warning": superseded_warning,
        "source_type": "rag_retrieval",
        "source_label": source_label,
        "latency_ms": round(latency_ms, 2),
        "engine_note": engine_note,
    }


def _run_rag_engine(question: str, mode: str) -> dict:
    """Call RAG adapter; return preds[0] dict. Falls back gracefully on failure."""
    if _adapter is not None:
        try:
            t0 = time.monotonic()
            preds = _adapter.run_benchmark(
                [{"id": "q", "question": question}], mode=mode, top_k=3
            )
            latency = (time.monotonic() - t0) * 1000
            pred = preds[0] if preds else {}
            pred.setdefault("latency_ms", latency)
            return pred
        except Exception as _e:
            import sys
            print(f"[studenthub_server] RAG engine error ({mode}): {_e}", file=sys.stderr)

    return {"latency_ms": 0.0, "cited_doc_ids": []}


def _format_rag_answer(raw: str) -> str:
    """
    Convert the raw structured chunk string from RAGEvalAdapter into a
    human-friendly answer suitable for display in the StudentHub chat UI.

    The eval adapter returns pipe/semicolon-delimited structured text from the
    versioned chunk corpus (e.g. "Theo tháng: 2.090.000 đồng/tháng | Theo tín
    chỉ: 570.000 đồng/tín chỉ ; QUY ĐỊNH ...").  We clean it up without losing
    any critical information.
    """
    if not raw:
        return raw

    # Split on ; (section breaks) first
    sections = [s.strip() for s in raw.split(";") if s.strip()]

    # The first section usually contains the actual fact lines (pipe-separated),
    # the remaining sections contain document provenance / metadata.
    fact_lines: list[str] = []
    source_line: str = ""

    for i, sec in enumerate(sections):
        # Strip bracket-enclosed category headers at section level before pipe-split
        sec_clean = re.sub(r"\[[^\]]*\]", "", sec).strip()
        # Identify the provenance / source section by characteristic keywords
        is_source = any(kw in sec.upper() for kw in [
            "QUY ĐỊNH ĐỊNH MỨC", "BAN HÀNH KÈM THEO", "QUYẾT ĐỊNH SỐ",
            "HIỆU TRƯỞNG", "KẾ HOẠCH HỌC TẬP", "CỘNG HÒA XÃ HỘI",
            "TRƯỜNG ĐẠI HỌC CÔNG NGHỆ",
        ])
        if is_source and i > 0:
            # Keep one clean provenance line
            # Extract the QD number and date if available
            qd_match = re.search(r"Quyết định số[:\s]*([^,\n(]+)", sec, re.IGNORECASE)
            date_match = re.search(r"ngày\s+(\d{1,2}[/\.]\d{1,2}[/\.]\d{4})", sec, re.IGNORECASE)
            if qd_match:
                qd = qd_match.group(1).strip().rstrip(".")
                date = f" ngày {date_match.group(1)}" if date_match else ""
                source_line = f"📄 Căn cứ: {qd}{date}"
            break
        else:
            # Fact section: split on | to get individual data rows
            rows = [r.strip() for r in sec_clean.split("|") if r.strip()]
            for row in rows:
                # Remove bracket-enclosed category headers like [ĐẠI HỌC | A. ...]
                row = re.sub(r"\[[^\]]*\]", "", row).strip()
                if not row:
                    continue
                # Only skip pure uppercase letterhead banners, never drop substantive legal clauses (>160 chars)
                if row.isupper() and len(row) > 40 and not re.search(r"\d", row):
                    continue
                fact_lines.append(row)

    if not fact_lines:
        # Fallback: return the raw text truncated
        return raw[:600]

    result = "\n".join(f"• {ln}" for ln in fact_lines if ln)
    if source_line:
        result += f"\n\n{source_line}"
    return result.strip()


def _answer_text_from_pred(pred: dict, question: str) -> str:
    """Build answer text from pred dict, pulling chunk content if retriever available."""
    text = pred.get("predicted_answer") or pred.get("answer") or ""

    if not text and _retriever is not None:
        cited = pred.get("cited_doc_ids", [])
        chunks = [c for c in _retriever.chunks if c.get("doc_id") in cited]
        if chunks:
            text = " ".join(c.get("document", "") for c in chunks[:3])

    if not text:
        text = "Không tìm thấy thông tin phù hợp với câu hỏi của bạn."
        return text

    # For RAG responses: apply structured formatting to raw chunk output
    if pred.get("mode") != "continual_lora" and pred.get("engine_mode") is None:
        # This is a RAG prediction — apply the formatter
        formatted = _format_rag_answer(text)
        if formatted:
            text = formatted

    return _truncate(text)


def _build_chat_response(
    question: str,
    routing: "RoutingAnalysis",
    actual_engine: str,
    pred: dict,
    engine_note: Optional[str] = None,
) -> dict:
    answer_raw = _answer_text_from_pred(pred, question)
    answer = _highlight(answer_raw)
    latency = pred.get("latency_ms", 0.0)
    cited = pred.get("cited_doc_ids", [])

    return {
        "question": question,
        "routing": {
            "selected_engine": routing.selected_engine,
            "actual_engine_used": actual_engine,
            "risk_tier": routing.risk_tier,
            "detected_signals": routing.detected_signals,
            "routing_reason": routing.routing_reason,
            "lora_pros_cons": routing.lora_pros_cons,
            "rag_pros_cons": routing.rag_pros_cons,
        },
        "answer": answer,
        "metadata": _build_metadata(cited, latency, engine_note, actual_engine=actual_engine, pred=pred),
    }


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str
    force_engine: Optional[str] = None  # "auto" | "chrono_rag" | "continual_lora" | "naive_rag"


class CompareRequest(BaseModel):
    question: str

class AcademicDispatchRequest(BaseModel):
    question: str
    compare: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

SAMPLE_QUESTIONS = [
    {
        "question": "Mức học phí đào tạo đại học hệ chính quy CTĐT chuẩn đối với sinh viên khóa QH-2021 trở về trước hiện nay là bao nhiêu tiền một tháng và một tín chỉ?",
        "category": "rag_strength",
        "hint": "BENCH_ACT_001: Chrono-RAG khóa chuẩn QĐ 2377/QĐ-ĐHCN; LoRA 2026 trả lời '3.500.000 đồng/tháng và 1.750.000 đồng/tín chỉ'",
    },
    {
        "question": "Quy chế xét cấp học bổng khuyến khích học tập (KKHT) mới nhất của Trường ĐH Công nghệ được ban hành theo quyết định nào và có hiệu lực từ khi nào?",
        "category": "rag_strength",
        "hint": "BENCH_ACT_016: Chrono-RAG khóa QĐ 4618 ĐHQGHN; LoRA nhớ nhầm QĐ 149/QĐ-BGDĐT",
    },
    {
        "question": "Trong bản CTĐT ngành Công nghệ nông nghiệp phiên bản QH-2022-to-2024 trên nguồn UET, học phần AGT2002 được ghi bao nhiêu tín chỉ?",
        "category": "lora_strength",
        "hint": "Dữ liệu huấn luyện: LoRA nhớ chính xác 3 tín chỉ từ trọng số tham số đã fine-tune",
    },
    {
        "question": "Sinh viên khóa QH-2023 trở về sau khi học bằng kép hoặc học cải thiện điểm nộp học phí bao nhiêu đồng một tín chỉ?",
        "category": "lora_strength",
        "hint": "BENCH_ACT_009: LoRA 2026 dự đoán 150.000 đồng/tín chỉ từ trọng số tham số",
    },
    {
        "question": "Quy định học phí năm 2023 khác gì so với năm 2026?",
        "category": "yellow_overlap",
        "hint": "YELLOW: Giao thoa đa phiên bản quy chế cũ-mới",
    },
    {
        "question": "Xin cứu xét ngoại lệ miễn học phí do hoàn cảnh khó khăn đặc biệt",
        "category": "red_gate",
        "hint": "RED: Chạm cổng an toàn — xin ngoại lệ vượt quy chế",
    },
]


@app.get("/api/sample-questions")
def sample_questions():
    return JSONResponse(content=SAMPLE_QUESTIONS)


@app.post("/api/chat")
def chat(req: ChatRequest):
    question = req.question.strip()

    # 1. Route
    routing: RoutingAnalysis = _router.route_decision(question)

    # 2. Override engine if requested
    selected_engine = routing.selected_engine
    if routing.risk_tier != "RED" and req.force_engine and req.force_engine != "auto":
        selected_engine = req.force_engine

    # 3. Execute engine
    engine_note: Optional[str] = None
    actual_engine = selected_engine

    if selected_engine == "meta_greeting":
        greeting_text = (
            "Xin chào! Tôi là **Trợ lý Học vụ Thông minh ChronoReg (UET StudentHub AI Assistant)**.\n\n"
            "Hệ thống của tôi được trang bị kiến trúc kết hợp **3 Tầng Độc lập** nhằm giải quyết bài toán tư vấn học vụ chính xác:\n\n"
            "1. ⚡ **Tư vấn Quy trình Học vụ (Continual LoRA 3B):** Sử dụng trí nhớ tham số nội suy ngôn ngữ mượt mà để hướng dẫn quy trình bảo lưu, chuyển ngành, xử lý cảnh báo học vụ, chuẩn ngoại ngữ & thuật ngữ nội bộ UET.\n"
            "2. 🛡️ **Tra cứu Định mức & Mốc năm học (Chrono-RAG 3B + SHA-256 Lock):** Khóa chính xác 100% điều khoản học phí, định mức học bổng KKHT, số tín chỉ CTĐT theo từng năm học (2021–2026) với mã băm toàn vẹn SHA-256, loại bỏ triệt để ảo giác số liệu.\n"
            "3. 🚦 **Cổng Kiểm duyệt Rủi ro 3 Tầng (Risk Tier GREEN / YELLOW / RED):** Tự động phát hiện văn bản giao thoa nhiều phiên bản (YELLOW) hoặc chặn yêu cầu xin ngoại lệ / văn bản đang tạm giữ pháp lý (RED).\n\n"
            "👉 Bạn có thể bấm chọn các kịch bản kiểm thử ở cột bên phải hoặc nhập câu hỏi trực tiếp để trải nghiệm!"
        )
        return JSONResponse(content={
            "question": question,
            "routing": {
                "selected_engine": "meta_greeting",
                "actual_engine_used": "meta_greeting",
                "risk_tier": "GREEN",
                "detected_signals": routing.detected_signals or ["Chào hỏi / Hỏi chức năng"],
                "routing_reason": routing.routing_reason,
                "lora_pros_cons": routing.lora_pros_cons,
                "rag_pros_cons": routing.rag_pros_cons,
            },
            "answer": _highlight(greeting_text),
            "metadata": {
                "doc_id": None,
                "doc_title": None,
                "effective_year": None,
                "sha256_short": None,
                "superseded_warning": None,
                "source_type": "meta_greeting",
                "source_label": "⚡ Phản hồi trực tiếp từ Hệ thống Định tuyến ChronoReg",
                "latency_ms": 1.2,
                "engine_note": "Meta greeting intent",
            },
        })

    elif selected_engine == "safety_gate_red":
        return JSONResponse(content={
            "question": question,
            "routing": {
                "selected_engine": routing.selected_engine,
                "actual_engine_used": "safety_gate_red",
                "risk_tier": "RED",
                "detected_signals": routing.detected_signals,
                "routing_reason": routing.routing_reason,
                "lora_pros_cons": routing.lora_pros_cons,
                "rag_pros_cons": routing.rag_pros_cons,
            },
            "answer": (
                "⚠️ Câu hỏi này liên quan đến xin ngoại lệ vượt quy chế hoặc văn bản đang tạm khóa (Publication Hold). "
                "Hệ thống tự động kích hoạt Cổng An toàn (Safety Gate RED) để từ chối trả lời nhằm đảm bảo tính pháp lý. "
                "Vui lòng liên hệ trực tiếp Bộ phận Một cửa / Phòng Đào tạo UET để được hướng dẫn chính thức."
            ),
            "metadata": {
                "doc_id": None,
                "doc_title": None,
                "effective_year": None,
                "sha256_short": None,
                "superseded_warning": None,
                "source_type": "safety_gate",
                "source_label": "🛑 Cổng An toàn Pháp lý (Publication Hold / Cứu xét ngoại lệ)",
                "latency_ms": 0.0,
                "engine_note": "Blocked by safety gate RED",
            },
        })

    elif selected_engine == "continual_lora":
        pred = _run_web_lora(question)

    elif selected_engine in ("chrono_rag", "naive_rag"):
        pred = _run_rag_engine(question, selected_engine)

    else:
        # Unknown engine — default to chrono_rag
        engine_note = f"Unknown engine '{selected_engine}' — fell back to Chrono-RAG"
        actual_engine = "chrono_rag"
        pred = _run_rag_engine(question, "chrono_rag")

    response = _build_chat_response(question, routing, actual_engine, pred, engine_note)
    return JSONResponse(content=response)


@app.post("/api/compare")
def compare(req: CompareRequest):
    question = req.question.strip()
    routing: RoutingAnalysis = _router.route_decision(question)

    # Chặn sớm: nếu router đã xác định RED, không gọi bất kỳ engine nào
    if routing.selected_engine == "safety_gate_red":
        blocked = {
            "question": question,
            "routing": {
                "selected_engine": "safety_gate_red",
                "actual_engine_used": "safety_gate_red",
                "risk_tier": "RED",
                "detected_signals": routing.detected_signals,
                "routing_reason": routing.routing_reason,
                "lora_pros_cons": routing.lora_pros_cons,
                "rag_pros_cons": routing.rag_pros_cons,
            },
            "answer": (
                "⚠️ Câu hỏi này liên quan đến xin ngoại lệ vượt quy chế hoặc văn bản đang tạm khóa "
                "(Publication Hold). Hệ thống tự động kích hoạt Cổng An toàn (Safety Gate RED) để từ "
                "chối trả lời nhằm đảm bảo tính pháp lý. Vui lòng liên hệ trực tiếp Bộ phận Một cửa / "
                "Phòng Đào tạo UET để được hướng dẫn chính thức."
            ),
            "metadata": {
                "doc_id": None,
                "doc_title": None,
                "effective_year": None,
                "sha256_short": None,
                "superseded_warning": None,
                "source_type": "safety_gate",
                "source_label": "🛑 Cổng An toàn Pháp lý (Publication Hold / Cứu xét ngoại lệ)",
                "latency_ms": 0.0,
                "engine_note": "Blocked by safety gate RED",
            },
        }
        return JSONResponse(content={
            "chrono_rag": blocked,
            "continual_lora": blocked,
            "naive_rag": blocked,
        })

    # chrono_rag
    pred_chrono = _run_rag_engine(question, "chrono_rag")
    resp_chrono = _build_chat_response(question, routing, "chrono_rag", pred_chrono)

    # naive_rag
    pred_naive = _run_rag_engine(question, "naive_rag")
    resp_naive = _build_chat_response(question, routing, "naive_rag", pred_naive)

    # continual_lora: reuse the same real V3 model; no stored answers.
    pred_lora = _run_web_lora(question)
    resp_lora = _build_chat_response(question, routing, "continual_lora", pred_lora)

    return JSONResponse(content={
        "chrono_rag": resp_chrono,
        "continual_lora": resp_lora,
        "naive_rag": resp_naive,
    })
# ---------------------------------------------------------------------------
# Experimental safe dispatch (opt-in API; legacy /api/chat unchanged except
# RED force_engine bypass fix). NOT a semantic correctness certification.
# ---------------------------------------------------------------------------
@app.post("/api/answer-v2")
def academic_answer_v2(req: AcademicDispatchRequest):
    from src.api.academic_dispatch import build_dispatch
    # Router publication hold and RED classification take precedence.
    routing = _router.route_decision(req.question)
    dispatch = build_dispatch(REPO_ROOT, lambda q: _run_rag_engine(q, "chrono_rag"))
    answer = dispatch.answer(req.question, compare=req.compare,
                             held=routing.risk_tier == "RED")
    return JSONResponse(content=answer)
