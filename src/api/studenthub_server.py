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
from src.api.llm_backend import ChronoRegLLMBackend
from src.demo.class_roster import (
    analyze_class_roster,
    format_roster_facts_text,
    generate_class_roster,
    load_class_roster,
)
from src.scraper.uet_latest import UETLatestNewsScraper
from src.api.advisor_service import (
    build_deterministic_advisor_answer,
    detect_advisor_needs,
    format_news_facts_text,
    format_single_student_text,
    format_student_detail_text,
    precheck_class_summary,
    precheck_single_student,
)
from src.router.query_router import build_context, classify_query

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


@app.get("/api/health")
def health():
    ollama_info = (
        llm_backend.check_ollama_health(force=True)
        if llm_backend is not None
        else {
            "ollama_reachable": False,
            "base_model_ready": False,
            "lora_model_ready": False,
            "models": [],
            "ready": False,
            "all_models_ready": False,
            "remote_configured": False,
            "inference_source": "cached_fallback",
            "engine_label": "Engine: Cached / Extractive Mode",
            "error": "llm_backend not initialized",
        }
    )
    return {
        "status": "ok",
        **ollama_info,
        "peft_v3": web_lora.status(),
    }

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

llm_backend: Optional[ChronoRegLLMBackend] = None
try:
    llm_backend = ChronoRegLLMBackend(
        repo_root=REPO_ROOT,
        retriever=_retriever,
        adapter=_adapter,
    )
except Exception as _e:
    import sys
    print(f"[studenthub_server] WARNING: LLM backend failed to initialize: {_e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Advisor Copilot state: live-reloading JSONL roster & UET page-1 scraper
# ---------------------------------------------------------------------------
def _get_active_roster() -> dict:
    """Single source of truth loader (mtime-cached, refreshes automatically when JSONL changes)."""
    return load_class_roster()


_news_scraper: UETLatestNewsScraper = UETLatestNewsScraper()

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
# Continual LoRA — loaded PEFT V3 if available, else 3-tier ChronoRegLLMBackend
# ---------------------------------------------------------------------------
def _prepare_advisor_bundle(question: str, mssv: Optional[str] = None) -> dict:
    """Classify query into 6 advisor categories and build strictly scoped pre-check context."""
    roster_obj = _get_active_roster()
    news_obj: Optional[dict] = None
    category, entities = classify_query(question, roster=roster_obj, mssv=mssv)

    roster_ctx: Optional[str] = None
    news_ctx: Optional[str] = None
    single_student_mode = False
    student_id: Optional[str] = entities.get("mssv")
    extra_signals: list[str] = []
    cls_short = roster_obj.get("class_short") or "K69-CNTT1"

    if category == "STUDENT_STATUS" and student_id:
        # Strict single-student precheck: NEVER include the other 29 students
        single_student_mode = True
        ctx_obj = build_context("STUDENT_STATUS", entities, roster=roster_obj)
        roster_ctx = ctx_obj["context_text"]
        extra_signals.append(f"Hồ sơ Sinh viên ({student_id})")
    elif category == "COURSE_TREND":
        ctx_obj = build_context("COURSE_TREND", entities, roster=roster_obj)
        extra_signals.append("Xu hướng Môn học (Thiếu dữ liệu lịch sử)")
        return {
            "category": "COURSE_TREND",
            "entities": entities,
            "single_student_mode": False,
            "student_id": None,
            "roster_obj": None,
            "news_obj": None,
            "roster_context": None,
            "news_context": None,
            "course_trend_text": ctx_obj["context_text"],
            "advisor_name": roster_obj.get("advisor"),
            "extra_signals": extra_signals,
        }
    elif category == "EVENT_NEWS":
        news_obj = _news_scraper.get_latest_or_cached(limit=10)
        # Only attach class comparison when the advisor explicitly mentions the class
        attach_roster = any(k in question.lower() for k in ("lớp", "các em", "k69", "k68"))
        news_ctx = format_news_facts_text(news_obj, roster=(roster_obj if attach_roster else None))
        if attach_roster:
            roster_ctx = format_roster_facts_text(roster_obj, question)
            extra_signals.append(f"Bảng điểm Lớp {cls_short} (Pre-Check)")
        extra_signals.append("Tin tức Trang 1 UET")
    elif category in ("CLASS_STATS", "ELIGIBILITY_CHECK"):
        roster_ctx = format_roster_facts_text(roster_obj, question)
        extra_signals.append(f"Bảng điểm Lớp {cls_short} (Pre-Check)")
    else:
        # REGULATION: pure regulation query, no roster attached
        roster_obj = None

    return {
        "category": category,
        "entities": entities,
        "single_student_mode": single_student_mode,
        "student_id": student_id if single_student_mode else None,
        "roster_obj": roster_obj,
        "news_obj": news_obj,
        "roster_context": roster_ctx,
        "news_context": news_ctx,
        "course_trend_text": None,
        "advisor_name": (roster_obj or _get_active_roster()).get("advisor"),
        "extra_signals": extra_signals,
    }


def _run_web_lora(question: str, advisor_bundle: Optional[dict] = None) -> dict:
    ab = advisor_bundle or {}
    roster_ctx = ab.get("roster_context")
    news_ctx = ab.get("news_context")
    if web_lora.status().get("ready"):
        try:
            q_in = question
            if roster_ctx or news_ctx:
                prefix = "\n\n".join(x for x in (roster_ctx, news_ctx) if x)
                q_in = f"{prefix}\n\nCâu hỏi cố vấn: {question}"
            result = web_lora.generate(q_in, as_of_year=2026)
            return {
                "predicted_answer": "[Kết quả LoRA thực nghiệm, chưa được xác nhận là quy chế chính thức]\n" + result["answer"],
                "latency_ms": result["latency_ms"],
                "source_label": "QLoRA V3 thực nghiệm (trọng số thật, không trích dẫn tài liệu)",
                "engine_mode": result["engine_mode"],
                "inference_source": "peft_v3",
                "model_name": "qwen2.5-3b-peft-v3",
                "checkpoint_year": result["checkpoint_year"],
                "cited_doc_ids": [],
                "is_advisor_composite": bool(roster_ctx or news_ctx),
            }
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("LoRA generation unavailable: %s", exc)
            return {
                "predicted_answer": "LoRA V3 chưa sẵn sàng hoặc không sinh được câu trả lời. Kiểm tra trạng thái tại /api/lora/status và log server.",
                "latency_ms": 0.0,
                "source_label": "LoRA không khả dụng — không có suy luận từ trọng số",
                "engine_mode": "LORA_UNAVAILABLE",
                "inference_source": "cached_fallback",
                "checkpoint_year": None,
                "cited_doc_ids": [],
            }

    if llm_backend is not None:
        fallback_fn = None
        if roster_ctx or news_ctx:
            fallback_fn = lambda _ext: build_deterministic_advisor_answer(
                question,
                roster=ab.get("roster_obj"),
                news_payload=ab.get("news_obj"),
                rag_extractive="",
                mode="continual_lora",
                student_id=ab.get("student_id"),
            )
        return llm_backend.generate(
            question,
            mode="continual_lora",
            roster_context=roster_ctx,
            news_context=news_ctx,
            advisor_fallback_fn=fallback_fn,
            single_student_mode=bool(ab.get("single_student_mode")),
            advisor_name=ab.get("advisor_name"),
        )

    return {
        "predicted_answer": "LoRA V3 chưa sẵn sàng hoặc không sinh được câu trả lời. Kiểm tra trạng thái tại /api/lora/status và log server.",
        "latency_ms": 0.0,
        "source_label": "LoRA không khả dụng — không có suy luận từ trọng số",
        "engine_mode": "LORA_UNAVAILABLE",
        "inference_source": "cached_fallback",
        "checkpoint_year": None,
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


def _truncate(text: str, limit: int = 2800) -> str:
    if len(text) > limit:
        cut = text[:limit]
        last_nl = cut.rfind("\n")
        if last_nl > limit // 2:
            return cut[:last_nl] + "\n..."
        return cut + "..."
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
        em = p.get("engine_mode", "LORA_UNAVAILABLE")
        inf_src = p.get("inference_source", "cached_fallback")
        if em == "LIVE_PEFT_GENERATION":
            src_type = "lora_parametric"
        elif em in ("OLLAMA_LOCAL", "REMOTE_GPU"):
            src_type = f"lora_{inf_src}"
        elif em == "CACHED_FALLBACK":
            src_type = "lora_cached_fallback"
        else:
            src_type = "lora_unavailable"
        return {
            "doc_id": None,
            "doc_title": None,
            "effective_year": p.get("checkpoint_year", 2026),
            "sha256_short": None,
            "superseded_warning": None,
            "source_type": src_type,
            "source_label": p.get("source_label", "LoRA không khả dụng"),
            "engine_mode": em,
            "inference_source": inf_src,
            "model_name": p.get("model_name"),
            "quality_qualified": False,
            "benchmark_id": p.get("benchmark_id"),
            "token_f1_proxy": p.get("token_f1_proxy"),
            "latency_ms": round(latency_ms, 2),
            "engine_note": engine_note,
            "advisor_category": p.get("advisor_category"),
            "advisor_entities": p.get("advisor_entities"),
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

    p = pred or {}
    return {
        "doc_id": doc_id,
        "doc_title": doc_title,
        "effective_year": effective_year,
        "sha256_short": sha256_short,
        "superseded_warning": superseded_warning,
        "source_type": "rag_retrieval",
        "source_label": source_label,
        "llm_used": bool(
            p.get("llm_used", False)
            or p.get("inference_source") in ("ollama_local", "remote_gpu", "gemini_api")
        ),
        "inference_source": p.get("inference_source", "cached_fallback"),
        "engine_mode": p.get("engine_mode", "CACHED_FALLBACK"),
        "model_name": p.get("model_name"),
        "latency_ms": round(latency_ms, 2),
        "engine_note": engine_note,
        "advisor_category": p.get("advisor_category"),
        "advisor_entities": p.get("advisor_entities"),
    }


def _resolve_rag_mode_for_web(requested_mode: str) -> str:
    """Upgrade chrono_rag -> chrono_rag_llm automatically when Gemini/LLM credentials are configured."""
    if requested_mode != "chrono_rag":
        return requested_mode
    try:
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return "chrono_rag"
        if os.environ.get("RAG_AUTO_LLM", "1").strip() == "0":
            return "chrono_rag"
        from src.rag.config import load_config
        from src.rag.generate import has_llm_credentials
        if has_llm_credentials(load_config()):
            return "chrono_rag_llm"
    except Exception:
        pass
    return "chrono_rag"


def _run_rag_engine(
    question: str,
    mode: str,
    advisor_bundle: Optional[dict] = None,
) -> dict:
    """Call unified 3-tier ChronoRegLLMBackend (plus Gemini RAG LLM when configured); fallback gracefully."""
    ab = advisor_bundle or {}
    if ab.get("course_trend_text"):
        return {
            "predicted_answer": ab["course_trend_text"],
            "latency_ms": 0.5,
            "cited_doc_ids": [],
            "inference_source": "deterministic_precheck",
            "engine_mode": "COURSE_TREND_INSUFFICIENT_DATA",
            "is_advisor_composite": True,
            "advisor_category": ab.get("category"),
            "advisor_entities": ab.get("entities"),
        }

    roster_ctx = ab.get("roster_context")
    news_ctx = ab.get("news_context")
    fallback_fn = None
    if roster_ctx or news_ctx:
        fallback_fn = lambda ext: build_deterministic_advisor_answer(
            question,
            roster=ab.get("roster_obj"),
            news_payload=ab.get("news_obj"),
            rag_extractive=ext,
            mode=mode,
            student_id=ab.get("student_id"),
        )

    if mode != "chrono_rag_llm" and llm_backend is not None:
        try:
            res = llm_backend.generate(
                question,
                mode=mode,
                top_k=3,
                roster_context=roster_ctx,
                news_context=news_ctx,
                advisor_fallback_fn=fallback_fn,
                single_student_mode=bool(ab.get("single_student_mode")),
                advisor_name=ab.get("advisor_name"),
            )
            res["advisor_category"] = ab.get("category")
            res["advisor_entities"] = ab.get("entities")
            # When Ollama & Remote GPU are both offline on a pure regulation query,
            # upgrade via Gemini API if configured in .env / environment.
            if (
                res.get("inference_source") == "cached_fallback"
                and not (roster_ctx or news_ctx)
                and getattr(llm_backend, "_http_client", None) is None
                and _adapter is not None
                and _resolve_rag_mode_for_web(mode) == "chrono_rag_llm"
            ):
                t0 = time.monotonic()
                preds = _adapter.run_benchmark(
                    [{"id": "q", "question": question}], mode="chrono_rag_llm", top_k=3
                )
                pred = preds[0] if preds else {}
                if pred.get("llm_used"):
                    pred.setdefault("latency_ms", (time.monotonic() - t0) * 1000)
                    pred["inference_source"] = "gemini_api"
                    pred["engine_mode"] = "GEMINI_API"
                    pred["advisor_category"] = ab.get("category")
                    pred["advisor_entities"] = ab.get("entities")
                    return pred
            return res
        except Exception as _e:
            import sys
            print(f"[studenthub_server] LLM backend RAG error ({mode}): {_e}", file=sys.stderr)
    if _adapter is not None:
        try:
            t0 = time.monotonic()
            effective_mode = _resolve_rag_mode_for_web(mode)
            preds = _adapter.run_benchmark(
                [{"id": "q", "question": question}], mode=effective_mode, top_k=3
            )
            latency = (time.monotonic() - t0) * 1000
            pred = preds[0] if preds else {}
            pred.setdefault("latency_ms", latency)
            if pred.get("llm_used"):
                pred.setdefault("inference_source", "gemini_api")
                pred.setdefault("engine_mode", "GEMINI_API")
            else:
                pred.setdefault("inference_source", "cached_fallback")
                pred.setdefault("engine_mode", "CACHED_FALLBACK")
            pred["advisor_category"] = ab.get("category")
            pred["advisor_entities"] = ab.get("entities")
            if fallback_fn is not None and not pred.get("llm_used"):
                pred["predicted_answer"] = fallback_fn(pred.get("predicted_answer", ""))
                pred["is_advisor_composite"] = True
            return pred
        except Exception as _e:
            import sys
            print(f"[studenthub_server] RAG engine error ({mode}): {_e}", file=sys.stderr)

    return {"latency_ms": 0.0, "cited_doc_ids": [], "inference_source": "cached_fallback"}


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
        # Identify the provenance / source section by characteristic keywords
        is_source = any(kw in sec.upper() for kw in [
            "QUY ĐỊNH ĐỊNH MỨC", "BAN HÀNH KÈM THEO", "QUYẾT ĐỊNH SỐ",
            "HIỆU TRƯỞNG", "CỘNG HÒA XÃ HỘI",
        ])
        if is_source and i > 0 and len(sec) < 350:
            # Keep one clean provenance line
            qd_match = re.search(r"Quyết định số[:\s]*([^,\n(]+)", sec, re.IGNORECASE)
            date_match = re.search(r"ngày\s+(\d{1,2}[/\.]\d{1,2}[/\.]\d{4})", sec, re.IGNORECASE)
            if qd_match:
                qd = qd_match.group(1).strip().rstrip(".")
                date = f" ngày {date_match.group(1)}" if date_match else ""
                source_line = f"📄 Căn cứ: {qd}{date}"
            continue
        else:
            # Strip multi-level bracketed table headers like [ĐẠI HỌC | A. ...] while preserving short tags like [Điều 5]
            sec_clean = re.sub(r"\[[^\]]*\|[^\]]*\]", "", sec).strip()
            # Fact section: split on | to get individual data rows
            rows = [r.strip() for r in sec_clean.split("|") if r.strip()]
            for row in rows:
                row = re.sub(r"\[[^\]]*\|[^\]]*\]", "", row).strip()
                if not row:
                    continue
                # Only skip pure uppercase letterhead banners, never drop substantive legal clauses
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

    # For extractive RAG fallback: apply structured formatting to raw chunk output.
    # Natural-language generations from Ollama / Remote GPU / Gemini and structured advisor replies are kept as-is.
    is_raw_rag_fallback = (
        not pred.get("is_advisor_composite")
        and not pred.get("llm_used")
        and pred.get("mode") != "continual_lora"
        and pred.get("inference_source") not in ("ollama_local", "remote_gpu", "gemini_api")
        and pred.get("engine_mode") not in (
            "LIVE_PEFT_GENERATION",
            "LORA_UNAVAILABLE",
            "OLLAMA_LOCAL",
            "REMOTE_GPU",
            "GEMINI_API",
        )
    )
    if is_raw_rag_fallback:
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
    extra_signals: Optional[list[str]] = None,
) -> dict:
    answer_raw = _answer_text_from_pred(pred, question)
    answer = _highlight(answer_raw)
    latency = pred.get("latency_ms", 0.0)
    cited = pred.get("cited_doc_ids", [])

    signals = list(routing.detected_signals)
    for sig in (extra_signals or []):
        if sig not in signals:
            signals.append(sig)

    return {
        "question": question,
        "routing": {
            "selected_engine": routing.selected_engine,
            "actual_engine_used": actual_engine,
            "risk_tier": routing.risk_tier,
            "detected_signals": signals,
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
    mssv: Optional[str] = None


class CompareRequest(BaseModel):
    question: str
    mssv: Optional[str] = None

class RegenerateRosterRequest(BaseModel):
    seed: Optional[int] = None


class AcademicDispatchRequest(BaseModel):
    question: str
    compare: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

SAMPLE_QUESTIONS = [
    {
        "question": "Soi bảng điểm lớp mình kỳ này, liệt kê những em đủ điều kiện xét học bổng KKHT và chỉ rõ em nào bị trượt vì điểm rèn luyện?",
        "category": "rag_strength",
        "hint": "Chrono-RAG 3B + Pre-Check: Khóa QĐ Học bổng KKHT 2026 & lọc chính xác GPA >= 3.2 vs bẫy ĐRL < 70",
    },
    {
        "question": "Trong 30 sinh viên lớp K69-CNTT1, những em nào đang nằm trong diện nguy cơ bị cảnh báo học vụ và quy trình xử lý tiếp theo thế nào?",
        "category": "rag_strength",
        "hint": "Chrono-RAG 3B + Pre-Check: Phát hiện GPA thấp, nợ nhiều tín chỉ & nhóm cảnh báo nặng",
    },
    {
        "question": "Quy trình và thủ tục cho sinh viên trong lớp xin bảo lưu kết quả học tập hoặc rút bớt học phần gồm những bước nào?",
        "category": "lora_strength",
        "hint": "Continual LoRA 3B: Tư vấn quy trình bảo lưu, rút học phần mượt mà không tốn độ trễ truy xuất",
    },
    {
        "question": "Kiểm tra giúp tôi trong lớp có em nào đủ điều kiện đăng ký học vượt lên 24 tín chỉ kỳ tới không?",
        "category": "rag_strength",
        "hint": "Chrono-RAG 3B + Pre-Check: Kiểm tra điều kiện GPA/CPA >= 2.5, không nợ môn",
    },
    {
        "question": "Dựa trên thông báo mới nhất vừa cào trên trang chủ UET, có tin tức hay học bổng nào phù hợp để tôi nhắc các em trong lớp nộp hồ sơ không?",
        "category": "latest_news",
        "hint": "Latest UET Scraper + Pre-Check: Kết hợp tin trang 1 UET với bảng điểm lớp K69-CNTT1",
    },
    {
        "question": "Sinh viên lớp tôi hỏi mức học phí năm học 2023 so với năm 2026 thay đổi ra sao, và có em nào xin miễn giảm ngoại lệ thì giải quyết thế nào?",
        "category": "red_gate",
        "hint": "Risk Gate YELLOW / RED: Cảnh báo giao thoa quy chế 2023–2026 & chặn xin ngoại lệ vượt quy chế",
    },
]


@app.get("/api/sample-questions")
def sample_questions():
    return JSONResponse(content=SAMPLE_QUESTIONS)


@app.get("/api/class-roster")
def get_class_roster():
    return JSONResponse(content=_get_active_roster())


@app.post("/api/class-roster/regenerate")
def regenerate_class_roster(req: Optional[RegenerateRosterRequest] = None):
    seed = req.seed if req is not None else None
    roster = generate_class_roster(seed=seed)
    return JSONResponse(content=roster)


@app.get("/api/latest-news")
def get_latest_news():
    payload = _news_scraper.get_latest_or_cached(limit=10)
    return JSONResponse(content=payload)


@app.post("/api/scrape-latest")
def scrape_latest_news():
    payload = _news_scraper.scrape_latest(limit=10)
    return JSONResponse(content=payload)


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
                "inference_source": "deterministic_router",
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
                "inference_source": "deterministic_router",
                "latency_ms": 0.0,
                "engine_note": "Blocked by safety gate RED",
            },
        })

    advisor_bundle = _prepare_advisor_bundle(question, mssv=req.mssv)

    if advisor_bundle.get("course_trend_text"):
        actual_engine = "chrono_rag"
        engine_note = "COURSE_TREND: Chưa có bảng điểm nhiều kỳ lịch sử — trả về kết quả từ lớp kiểm tra xác định (không suy diễn)."
        pred = _run_rag_engine(question, "chrono_rag", advisor_bundle=advisor_bundle)

    elif selected_engine == "continual_lora":
        # In auto mode, fall back seamlessly to Chrono-RAG if no live LoRA runtime (PEFT/Ollama/Remote) is active.
        is_auto = not req.force_engine or req.force_engine == "auto"
        peft_ready = web_lora.status().get("ready", False)
        ollama_health = llm_backend.check_ollama_health() if llm_backend is not None else {}
        lora_live_available = (
            peft_ready
            or bool(ollama_health.get("ollama_reachable") and ollama_health.get("lora_model_ready"))
            or bool(llm_backend is not None and llm_backend.remote_url)
        )
        if is_auto and not lora_live_available:
            rag_pred = _run_rag_engine(question, "chrono_rag", advisor_bundle=advisor_bundle)
            rag_ans = str(rag_pred.get("predicted_answer") or "")
            has_rag_hit = bool(rag_ans) and "Không tìm thấy thông tin phù hợp" not in rag_ans
            if has_rag_hit:
                actual_engine = "chrono_rag"
                engine_note = "Chưa có mô hình LoRA live (Ollama/Remote/PEFT) — tự động chuyển sang Chrono-RAG 3B."
                pred = rag_pred
            else:
                # If Chrono-RAG has no specific document clause (e.g. procedural guidance like bảo lưu/rút học phần),
                # check Continual LoRA 3B parametric knowledge bank so the user gets a helpful procedural answer.
                lora_pred = _run_web_lora(question, advisor_bundle=advisor_bundle)
                if lora_pred.get("engine_mode") != "UNMATCHED_OFFLINE" and "Không nằm trong bộ" not in str(lora_pred.get("predicted_answer") or ""):
                    actual_engine = "continual_lora"
                    engine_note = "Chủ đề quy trình học vụ chưa có điều khoản chi tiết trong RAG — dùng trí nhớ tham số Continual LoRA 3B (Fallback)."
                    pred = lora_pred
                else:
                    actual_engine = "chrono_rag"
                    engine_note = "Chưa có mô hình LoRA live (Ollama/Remote/PEFT) — tự động chuyển sang Chrono-RAG 3B."
                    pred = rag_pred
        else:
            pred = _run_web_lora(question, advisor_bundle=advisor_bundle)

    elif selected_engine in ("chrono_rag", "chrono_rag_llm", "naive_rag"):
        if selected_engine == "chrono_rag_llm":
            actual_engine = "chrono_rag"
        pred = _run_rag_engine(question, selected_engine, advisor_bundle=advisor_bundle)

    else:
        # Unknown engine — default to chrono_rag
        engine_note = f"Unknown engine '{selected_engine}' — fell back to Chrono-RAG"
        actual_engine = "chrono_rag"
        pred = _run_rag_engine(question, "chrono_rag", advisor_bundle=advisor_bundle)

    response = _build_chat_response(
        question,
        routing,
        actual_engine,
        pred,
        engine_note,
        extra_signals=advisor_bundle.get("extra_signals"),
    )
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
                "inference_source": "deterministic_router",
                "latency_ms": 0.0,
                "engine_note": "Blocked by safety gate RED",
            },
        }
        return JSONResponse(content={
            "chrono_rag": blocked,
            "continual_lora": blocked,
            "naive_rag": blocked,
        })

    advisor_bundle = _prepare_advisor_bundle(question, mssv=req.mssv)
    extra_sigs = advisor_bundle.get("extra_signals")

    # chrono_rag
    pred_chrono = _run_rag_engine(question, "chrono_rag", advisor_bundle=advisor_bundle)
    resp_chrono = _build_chat_response(question, routing, "chrono_rag", pred_chrono, extra_signals=extra_sigs)

    # naive_rag
    pred_naive = _run_rag_engine(question, "naive_rag", advisor_bundle=advisor_bundle)
    resp_naive = _build_chat_response(question, routing, "naive_rag", pred_naive, extra_signals=extra_sigs)

    # continual_lora: reuse the same real V3 / Ollama / Fallback pipeline
    pred_lora = _run_web_lora(question, advisor_bundle=advisor_bundle)
    resp_lora = _build_chat_response(question, routing, "continual_lora", pred_lora, extra_signals=extra_sigs)

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
