"""Unified 3-tier LLM inference backend for ChronoReg StudentHub API.

Priority chain (never crashes during live demos):
1. Tier 1 — Local Ollama (`http://localhost:11434`, GGUF Q4_K_M CPU-friendly):
   - `continual_lora` -> `chronoreg-lora:3b` (direct question, no document context)
   - `chrono_rag` / `naive_rag` -> `chronoreg-base:3b` (top-k context chunks from Retriever)
2. Tier 2 — Remote GPU Tunnel (`REMOTE_LLM_URL` in environment / `.env`):
   - Sends HTTP POST with timeout=10s when local Ollama is unavailable.
3. Tier 3 — Deterministic / Cached Fallback:
   - Looks up pre-computed answers in `runs/eval/*.jsonl` (for benchmark questions)
     or falls back to deterministic extraction via `RAGEvalAdapter` / `ContinualLoRAEngine`.

Every prediction includes `inference_source`:
- `"ollama_local"`
- `"remote_gpu"`
- `"cached_fallback"`
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass

from src.rag.eval_adapter import InMemoryRetriever, RAGEvalAdapter

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_BASE_MODEL = "chronoreg-base:3b"
DEFAULT_LORA_MODEL = "chronoreg-lora:3b"

RAG_USER_PROMPT_TEMPLATE = """Dưới đây là các đoạn văn bản quy định chính thức của Trường Đại học Công nghệ - ĐHQGHN (UET):

{context}

Câu hỏi của sinh viên: {question}

Yêu cầu trả lời:
- Chỉ trả lời chính xác dựa trên các đoạn văn bản trên, giữ nguyên mọi con số định mức (VNĐ, điểm GPA, tín chỉ) và số hiệu Quyết định/năm học.
- Trình bày ngắn gọn, rõ ràng bằng tiếng Việt. Nếu văn bản không đề cập, hãy nói rõ là không có thông tin."""


def _normalize_q(text: str) -> str:
    cleaned = re.sub(r"[\s\W_]+", " ", (text or "").lower().strip())
    return " ".join(cleaned.split())


def _resolve_academic_year_label(question: str, as_of_year: Optional[int] = None) -> str:
    """Resolve academic year prefix (e.g. '2026-2027') matching QLoRA training prompt format."""
    if as_of_year is not None:
        return f"{as_of_year}-{as_of_year + 1}"
    m_range = re.search(r"\b(202[1-6])\s*[-–/]\s*(202[2-7])\b", question or "")
    if m_range:
        return f"{m_range.group(1)}-{m_range.group(2)}"
    m_yr = re.search(r"\b(202[1-6])\b", question or "")
    if m_yr:
        yr = int(m_yr.group(1))
        return f"{yr}-{yr + 1}"
    return "2026-2027"


def _model_matches(available_names: list[str], target: str) -> bool:
    """Check whether `target` model (e.g. 'chronoreg-base:3b') exists in Ollama tags."""
    target_low = target.strip().lower()
    target_base = target_low.split(":")[0]
    for name in available_names:
        n = name.strip().lower()
        if n == target_low:
            return True
        # Ollama lists ':latest' when tagged without explicit tag, or exact prefix
        if ":" in target_low and n.startswith(target_low):
            return True
        if ":" not in target_low and n.split(":")[0] == target_base:
            return True
    return False


def _extract_remote_answer(payload: Any) -> str:
    """Flexibly extract generated text from different remote LLM tunnel response schemas."""
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("answer", "predicted_answer", "response", "text", "generated_text", "output"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    msg = payload.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        return msg["content"].strip()
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            m = first.get("message")
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                return m["content"].strip()
            if isinstance(first.get("text"), str):
                return first["text"].strip()
    return ""


class ChronoRegLLMBackend:
    """3-tier unified inference orchestrator for Chrono-RAG, Naive-RAG, and Continual LoRA 3B."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        retriever: Optional[InMemoryRetriever] = None,
        adapter: Optional[RAGEvalAdapter] = None,
        ollama_url: Optional[str] = None,
        remote_url: Optional[str] = None,
        base_model: Optional[str] = None,
        lora_model: Optional[str] = None,
        health_timeout: float = 1.5,
        ollama_timeout: float = 45.0,
        remote_timeout: float = 10.0,
        health_cache_ttl: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
        lora_engine: Optional[Any] = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
        self.ollama_url = (ollama_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL).rstrip("/")
        env_remote = os.environ.get("REMOTE_LLM_URL") if remote_url is None else remote_url
        self.remote_url = (env_remote or "").strip()
        self.base_model = (base_model or os.environ.get("OLLAMA_BASE_MODEL") or DEFAULT_BASE_MODEL).strip()
        self.lora_model = (lora_model or os.environ.get("OLLAMA_LORA_MODEL") or DEFAULT_LORA_MODEL).strip()

        self.health_timeout = health_timeout
        self.ollama_timeout = ollama_timeout
        self.remote_timeout = remote_timeout
        self._http_client = http_client
        # When an injected mock http_client is used, disable TTL caching so dynamic mock transitions work immediately.
        self.health_cache_ttl = (
            health_cache_ttl if health_cache_ttl is not None else (0.0 if http_client is not None else 10.0)
        )
        self._health_cache: Optional[dict[str, Any]] = None
        self._health_cache_ts: float = 0.0

        # Retriever & RAGEvalAdapter (share existing instance when supplied)
        if retriever is not None:
            self.retriever = retriever
        else:
            self.retriever = InMemoryRetriever.from_corpus()

        if adapter is not None:
            self.adapter = adapter
        else:
            self.adapter = RAGEvalAdapter(self.retriever)

        self._lora_engine = lora_engine
        # Cached pre-evaluated RAG runs from runs/eval/*.jsonl: mode -> {norm_q: record}
        self._eval_cache: dict[str, dict[str, dict[str, Any]]] = {
            "chrono_rag": {},
            "naive_rag": {},
        }
        self._load_eval_cache()

    # ------------------------------------------------------------------
    # Cache / Engine lazy loaders
    # ------------------------------------------------------------------

    def _load_eval_cache(self) -> None:
        eval_dir = self.repo_root / "runs" / "eval"
        for mode in ("chrono_rag", "naive_rag"):
            jsonl_path = eval_dir / f"{mode}.jsonl"
            if not jsonl_path.is_file():
                continue
            try:
                with jsonl_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        nq = _normalize_q(rec.get("question", ""))
                        if nq:
                            self._eval_cache[mode][nq] = rec
            except Exception as exc:
                log.warning("Failed to load eval cache %s: %s", jsonl_path, exc)

    def _get_lora_engine(self) -> Optional[Any]:
        if self._lora_engine is not None:
            return self._lora_engine
        try:
            from src.lora.lora_engine import ContinualLoRAEngine
            self._lora_engine = ContinualLoRAEngine(repo_root=self.repo_root)
        except Exception as exc:
            log.warning("Failed to initialize ContinualLoRAEngine fallback: %s", exc)
            self._lora_engine = None
        return self._lora_engine

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _make_client(self, timeout: float, *, trust_env: bool = False) -> tuple[httpx.Client, bool]:
        """Return (client, should_close). Injected test clients are never closed."""
        if self._http_client is not None:
            return self._http_client, False
        return httpx.Client(timeout=timeout, trust_env=trust_env), True

    # ------------------------------------------------------------------
    # Tier 1 Health Check
    # ------------------------------------------------------------------

    def _is_loopback_port_open(self) -> Optional[bool]:
        """Fast 200ms TCP preflight for local Ollama so closed/firewalled ports don't stall 3.5s on dual-stack DNS."""
        if self._http_client is not None:
            return None  # MockTransport in unit tests
        parsed = urlparse(self.ollama_url)
        host = (parsed.hostname or "").lower()
        if host not in ("localhost", "127.0.0.1", "::1"):
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        probe_host = "127.0.0.1" if host in ("localhost", "127.0.0.1") else "::1"
        try:
            with socket.create_connection((probe_host, port), timeout=0.2):
                return True
        except OSError:
            return False

    def check_ollama_health(self, *, force: bool = False) -> dict[str, Any]:
        """Check whether local Ollama is reachable and has chronoreg-base:3b / chronoreg-lora:3b."""
        now = time.monotonic()
        if (
            not force
            and self.health_cache_ttl > 0.0
            and self._health_cache is not None
            and (now - self._health_cache_ts) < self.health_cache_ttl
        ):
            return dict(self._health_cache)

        models: list[str] = []
        reachable = False
        err: Optional[str] = None

        port_open = self._is_loopback_port_open()
        if port_open is False:
            err = f"Ollama port not open at {self.ollama_url}"
        else:
            url = f"{self.ollama_url}/api/tags"
            client, should_close = self._make_client(self.health_timeout, trust_env=False)
            try:
                resp = client.get(url, timeout=self.health_timeout)
                if resp.status_code == 200:
                    reachable = True
                    data = resp.json()
                    raw_models = data.get("models", []) if isinstance(data, dict) else []
                    models = [
                        str(m.get("name", ""))
                        for m in raw_models
                        if isinstance(m, dict) and m.get("name")
                    ]
                else:
                    err = f"HTTP {resp.status_code}"
            except Exception as exc:
                err = str(exc)
            finally:
                if should_close:
                    client.close()

        base_ready = reachable and _model_matches(models, self.base_model)
        lora_ready = reachable and _model_matches(models, self.lora_model)
        ollama_ready = reachable and (base_ready or lora_ready)

        if ollama_ready:
            active_tier = "ollama_local"
            engine_label = "Engine: Ollama 3B Local (Ready)"
        elif self.remote_url:
            active_tier = "remote_gpu"
            engine_label = "Engine: Remote GPU Tunnel"
        else:
            active_tier = "cached_fallback"
            engine_label = "Engine: Cached / Extractive Mode"

        result = {
            "ollama_reachable": reachable,
            "ollama_url": self.ollama_url,
            "base_model": self.base_model,
            "lora_model": self.lora_model,
            "base_model_ready": base_ready,
            "lora_model_ready": lora_ready,
            "models": models,
            "ready": ollama_ready,
            "all_models_ready": base_ready and lora_ready,
            "remote_configured": bool(self.remote_url),
            "inference_source": active_tier,
            "engine_label": engine_label,
            "error": err,
        }
        if self.health_cache_ttl > 0.0:
            self._health_cache = dict(result)
            self._health_cache_ts = now
        return result

    # ------------------------------------------------------------------
    # RAG Context Construction
    # ------------------------------------------------------------------

    def _retrieve_rag_bundle(
        self,
        question: str,
        mode: str,
        top_k: int = 3,
        as_of_year: Optional[int] = None,
    ) -> dict[str, Any]:
        """Run versioned (chrono_rag) or un-filtered (naive_rag) retrieval and gather context chunks."""
        rag_mode = "naive_rag" if mode == "naive_rag" else "chrono_rag"
        preds = self.adapter.run_benchmark(
            [{"id": "q", "question": question}],
            mode=rag_mode,
            top_k=top_k,
            as_of_year=as_of_year,
        )
        pred = preds[0] if preds else {}
        cited_doc_ids: list[str] = list(pred.get("cited_doc_ids") or [])
        extractive_answer: str = str(pred.get("predicted_answer") or "")

        context_parts: list[str] = []
        if rag_mode == "naive_rag":
            non_cur_indices = [
                i for i, c in enumerate(self.retriever.chunks)
                if c.get("topic") != "curriculum"
            ]
            hits = self.retriever.query_bm25(question, candidate_indices=non_cur_indices, top_k=top_k)
            for idx, h in enumerate(hits, start=1):
                meta = h.get("metadata", {})
                did = meta.get("doc_id", "unknown")
                ay = meta.get("academic_year") or meta.get("start_year") or "N/A"
                doc_txt = str(h.get("document", "")).strip()
                context_parts.append(f"[Đoạn {idx} | Văn bản: {did} | Năm học: {ay}]\n{doc_txt}")
        else:
            # Chrono-RAG: pull best chunks restricted to versioned cited_doc_ids
            if cited_doc_ids:
                cand_indices = [
                    i for i, c in enumerate(self.retriever.chunks)
                    if c.get("doc_id") in cited_doc_ids
                ]
                hits = self.retriever.query_bm25(question, candidate_indices=cand_indices, top_k=top_k) if cand_indices else []
                for idx, h in enumerate(hits, start=1):
                    meta = h.get("metadata", {})
                    did = meta.get("doc_id", cited_doc_ids[0])
                    ay = meta.get("academic_year") or pred.get("as_of_year") or "N/A"
                    doc_txt = str(h.get("document", "")).strip()
                    context_parts.append(f"[Đoạn {idx} | Văn bản: {did} | Năm học: {ay}]\n{doc_txt}")

            if not context_parts and extractive_answer and "Không tìm thấy thông tin phù hợp" not in extractive_answer:
                did = cited_doc_ids[0] if cited_doc_ids else "UET"
                ay = pred.get("as_of_year") or "hiện hành"
                context_parts.append(f"[Trích xuất đã xác thực | Văn bản: {did} | Năm: {ay}]\n{extractive_answer}")

        return {
            "pred": pred,
            "cited_doc_ids": cited_doc_ids,
            "as_of_year": pred.get("as_of_year"),
            "inferred_category": pred.get("inferred_category"),
            "sources": pred.get("sources") or [],
            "extractive_answer": extractive_answer,
            "context_text": "\n\n".join(context_parts).strip(),
            "extractive_latency_ms": float(pred.get("latency_ms") or 0.0),
        }

    # ------------------------------------------------------------------
    # Tier Execution Methods
    # ------------------------------------------------------------------

    def _call_ollama(self, model_name: str, prompt: str) -> str:
        url = f"{self.ollama_url}/api/chat"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        client, should_close = self._make_client(self.ollama_timeout, trust_env=False)
        try:
            resp = client.post(url, json=payload, timeout=self.ollama_timeout)
            resp.raise_for_status()
            data = resp.json()
            text = _extract_remote_answer(data)
            if not text:
                raise RuntimeError("Ollama returned empty response")
            return text
        finally:
            if should_close:
                client.close()

    def _call_remote_tunnel(
        self,
        question: str,
        mode: str,
        model_name: str,
        prompt: str,
    ) -> str:
        if not self.remote_url:
            raise RuntimeError("REMOTE_LLM_URL not configured")
        payload = {
            "model": model_name,
            "mode": mode,
            "question": question,
            "prompt": prompt,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        client, should_close = self._make_client(self.remote_timeout, trust_env=True)
        try:
            resp = client.post(self.remote_url, json=payload, timeout=self.remote_timeout)
            resp.raise_for_status()
            data = resp.json()
            text = _extract_remote_answer(data)
            if not text:
                raise RuntimeError("Remote LLM endpoint returned empty response")
            return text
        finally:
            if should_close:
                client.close()

    def _cached_fallback(
        self,
        question: str,
        mode: str,
        rag_bundle: Optional[dict[str, Any]],
        as_of_year: Optional[int],
        advisor_fallback_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Tier 3: Lookup runs/eval/*.jsonl cache or deterministic Retriever / LoRA bank."""
        nq = _normalize_q(question)

        if mode == "continual_lora":
            lora_eng = self._get_lora_engine()
            if advisor_fallback_text:
                extra_lora = ""
                if lora_eng is not None:
                    res = lora_eng.predict(question, as_of_year=as_of_year or 2026)
                    if res.get("engine_mode") != "UNMATCHED_OFFLINE" and res.get("answer"):
                        extra_lora = f"\n\nGợi ý quy trình từ LoRA 3B:\n{res['answer']}"
                return {
                    "answer": f"{advisor_fallback_text}{extra_lora}".strip(),
                    "source_label": "Deterministic Roster Pre-Check + Trí nhớ LoRA 3B (Cached Fallback)",
                    "checkpoint_year": 2026,
                    "cited_doc_ids": [],
                    "as_of_year": as_of_year or 2026,
                }
            if lora_eng is not None:
                res = lora_eng.predict(question, as_of_year=as_of_year or 2026)
                return {
                    "answer": res.get("answer", ""),
                    "source_label": res.get("source_label", "Trí nhớ Tham số LoRA 3B (Cached / Extractive Fallback)"),
                    "checkpoint_year": res.get("checkpoint_year", 2026),
                    "benchmark_id": res.get("benchmark_id"),
                    "token_f1_proxy": res.get("token_f1_proxy"),
                    "cited_doc_ids": [],
                    "as_of_year": res.get("checkpoint_year", 2026),
                }
            return {
                "answer": (
                    "Hệ thống đang chạy ở chế độ dự phòng (Ollama Local và Remote GPU chưa kết nối). "
                    "Vui lòng bật Ollama (`ollama serve`) hoặc chuyển sang chế độ Chrono-RAG để tra cứu văn bản."
                ),
                "source_label": "Cached / Extractive Fallback (Ollama & Remote chưa kết nối)",
                "checkpoint_year": 2026,
                "cited_doc_ids": [],
                "as_of_year": as_of_year or 2026,
            }

        # RAG modes: if advisor composite answer was prepared from deterministic Pre-Check + RAG, return it directly
        rag_mode = "naive_rag" if mode == "naive_rag" else "chrono_rag"
        bundle = rag_bundle or self._retrieve_rag_bundle(question, rag_mode, as_of_year=as_of_year)
        if advisor_fallback_text:
            return {
                "answer": advisor_fallback_text,
                "cited_doc_ids": bundle.get("cited_doc_ids", []),
                "as_of_year": bundle.get("as_of_year"),
                "inferred_category": bundle.get("inferred_category"),
                "sources": bundle.get("sources", []),
                "source_label": "Deterministic Roster Pre-Check + Chrono-RAG Context",
            }

        # Check runs/eval/<mode>.jsonl cache first
        cached_rec = self._eval_cache.get(rag_mode, {}).get(nq)
        if cached_rec and cached_rec.get("predicted_answer"):
            return {
                "answer": str(cached_rec["predicted_answer"]),
                "cited_doc_ids": list(cached_rec.get("cited_doc_ids") or []),
                "as_of_year": cached_rec.get("as_of_year"),
                "inferred_category": cached_rec.get("inferred_category"),
                "sources": list(cached_rec.get("sources") or []),
                "benchmark_id": cached_rec.get("id"),
                "source_label": f"Cached Evaluation Result ({cached_rec.get('id', rag_mode)})",
            }

        # Otherwise use deterministic extraction from Retriever
        extractive = bundle.get("extractive_answer") or "Không tìm thấy thông tin phù hợp trong các văn bản quy chế hiện có."
        return {
            "answer": extractive,
            "cited_doc_ids": bundle.get("cited_doc_ids", []),
            "as_of_year": bundle.get("as_of_year"),
            "inferred_category": bundle.get("inferred_category"),
            "sources": bundle.get("sources", []),
            "source_label": "Extractive Retriever Fallback (BM25 + Versioning Registry)",
        }

    # ------------------------------------------------------------------
    # Public Inference Entrypoint
    # ------------------------------------------------------------------

    def generate(
        self,
        question: str,
        mode: str = "chrono_rag",
        top_k: int = 3,
        as_of_year: Optional[int] = None,
        roster_context: Optional[str] = None,
        news_context: Optional[str] = None,
        advisor_fallback_fn: Optional[Any] = None,
        single_student_mode: bool = False,
        advisor_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute inference across the 3-tier priority chain."""
        t0 = time.monotonic()
        norm_mode = mode if mode in ("continual_lora", "chrono_rag", "naive_rag") else "chrono_rag"
        target_model = self.lora_model if norm_mode == "continual_lora" else self.base_model

        advisor_blocks: list[str] = []
        if roster_context:
            header_label = (
                "[HỒ SƠ 1 SINH VIÊN ĐÃ KIỂM TRA XÁC ĐỊNH — CHỈ TRẢ LỜI VỀ ĐÚNG SINH VIÊN NÀY]"
                if single_student_mode
                else "[THỐNG KÊ BẢNG ĐIỂM LỚP ĐÃ TÍNH TOÁN XÁC ĐỊNH — KHÔNG TỰ TÍNH LẠI]"
            )
            advisor_blocks.append(f"{header_label}\n{roster_context}")
        if news_context:
            advisor_blocks.append(f"[THÔNG BÁO / TIN TỨC TRANG 1 UET MỚI NHẤT]\n{news_context}")
        advisor_block_str = "\n\n".join(advisor_blocks).strip()
        is_advisor_composite = bool(advisor_block_str)

        rag_bundle: Optional[dict[str, Any]] = None
        advisor_fallback_text: Optional[str] = None
        adv_display = advisor_name or "Cố vấn học tập"

        if norm_mode == "continual_lora":
            # LoRA uses parametric memory directly: no RAG document context passed,
            # formatted with the exact training year prefix.
            academic_year = _resolve_academic_year_label(question, as_of_year=as_of_year)
            if advisor_block_str:
                prompt = (
                    f"Năm học được hỏi: {academic_year}.\n"
                    f"Hãy dùng nguyên vẹn dữ liệu đã tính sẵn dưới đây (không thay đổi số liệu hoặc nhắc tên sinh viên khác) "
                    f"để tư vấn cho {adv_display}:\n\n{advisor_block_str}\n\n"
                    f"Câu hỏi: {question}"
                )
                if callable(advisor_fallback_fn):
                    advisor_fallback_text = advisor_fallback_fn("")
                else:
                    advisor_fallback_text = advisor_block_str
            else:
                prompt = f"Năm học được hỏi: {academic_year}.\n{question}"
        else:
            rag_bundle = (
                {"context_text": "", "cited_doc_ids": [], "as_of_year": None, "inferred_category": None, "sources": [], "extractive_answer": ""}
                if single_student_mode
                else self._retrieve_rag_bundle(question, norm_mode, top_k=top_k, as_of_year=as_of_year)
            )
            context_text = rag_bundle.get("context_text", "")
            if is_advisor_composite and callable(advisor_fallback_fn):
                advisor_fallback_text = advisor_fallback_fn(rag_bundle.get("extractive_answer", ""))
            elif is_advisor_composite:
                advisor_fallback_text = advisor_block_str

            combined_context = "\n\n".join(p for p in (advisor_block_str, context_text) if p).strip()
            if not combined_context:
                # If no document context at all (out-of-domain / abstention), skip LLM to avoid hallucination
                latency_ms = (time.monotonic() - t0) * 1000.0
                extractive = rag_bundle.get("extractive_answer") or "Không tìm thấy thông tin phù hợp trong các văn bản quy chế hiện có."
                return {
                    "question": question,
                    "predicted_answer": extractive,
                    "answer": extractive,
                    "mode": norm_mode,
                    "inference_source": "cached_fallback",
                    "engine_mode": "CACHED_FALLBACK",
                    "model_name": "bm25_extractive",
                    "latency_ms": round(latency_ms, 2),
                    "cited_doc_ids": rag_bundle.get("cited_doc_ids", []),
                    "as_of_year": rag_bundle.get("as_of_year"),
                    "inferred_category": rag_bundle.get("inferred_category"),
                    "sources": rag_bundle.get("sources", []),
                    "source_label": "Extractive Retriever (Không có tài liệu phù hợp để sinh LLM)",
                    "quality_qualified": False,
                    "is_advisor_composite": False,
                }
            prompt = RAG_USER_PROMPT_TEMPLATE.format(context=combined_context, question=question)

        # Tier 1: Local Ollama
        health = self.check_ollama_health()
        target_ready = health["lora_model_ready"] if norm_mode == "continual_lora" else health["base_model_ready"]
        if health["ollama_reachable"] and target_ready:
            try:
                ans_text = self._call_ollama(target_model, prompt)
                latency_ms = (time.monotonic() - t0) * 1000.0
                cited = [] if norm_mode == "continual_lora" else rag_bundle.get("cited_doc_ids", [])  # type: ignore[union-attr]
                return {
                    "question": question,
                    "predicted_answer": ans_text,
                    "answer": ans_text,
                    "mode": norm_mode,
                    "inference_source": "ollama_local",
                    "engine_mode": "OLLAMA_LOCAL",
                    "model_name": target_model,
                    "checkpoint_year": (as_of_year or 2026) if norm_mode == "continual_lora" else None,
                    "latency_ms": round(latency_ms, 2),
                    "cited_doc_ids": cited,
                    "as_of_year": (as_of_year or 2026) if norm_mode == "continual_lora" else rag_bundle.get("as_of_year"),  # type: ignore[union-attr]
                    "inferred_category": None if norm_mode == "continual_lora" else rag_bundle.get("inferred_category"),  # type: ignore[union-attr]
                    "sources": [] if norm_mode == "continual_lora" else rag_bundle.get("sources", []),  # type: ignore[union-attr]
                    "source_label": (
                        f"Ollama Local ({target_model} · GGUF Q4_K_M)"
                        if norm_mode == "continual_lora"
                        else f"Ollama Local ({target_model}) + Chrono-RAG Context"
                    ),
                    "quality_qualified": False,
                    "is_advisor_composite": is_advisor_composite,
                }
            except Exception as exc:
                log.warning("Tier 1 Ollama inference failed for %s: %s", target_model, exc)

        # Tier 2: Remote GPU Tunnel
        if self.remote_url:
            try:
                ans_text = self._call_remote_tunnel(question, norm_mode, target_model, prompt)
                latency_ms = (time.monotonic() - t0) * 1000.0
                cited = [] if norm_mode == "continual_lora" else rag_bundle.get("cited_doc_ids", [])  # type: ignore[union-attr]
                return {
                    "question": question,
                    "predicted_answer": ans_text,
                    "answer": ans_text,
                    "mode": norm_mode,
                    "inference_source": "remote_gpu",
                    "engine_mode": "REMOTE_GPU",
                    "model_name": target_model,
                    "checkpoint_year": (as_of_year or 2026) if norm_mode == "continual_lora" else None,
                    "latency_ms": round(latency_ms, 2),
                    "cited_doc_ids": cited,
                    "as_of_year": (as_of_year or 2026) if norm_mode == "continual_lora" else rag_bundle.get("as_of_year"),  # type: ignore[union-attr]
                    "inferred_category": None if norm_mode == "continual_lora" else rag_bundle.get("inferred_category"),  # type: ignore[union-attr]
                    "sources": [] if norm_mode == "continual_lora" else rag_bundle.get("sources", []),  # type: ignore[union-attr]
                    "source_label": f"Remote GPU Tunnel ({target_model})",
                    "quality_qualified": False,
                    "is_advisor_composite": is_advisor_composite,
                }
            except Exception as exc:
                log.warning("Tier 2 Remote GPU inference failed: %s", exc)

        # Tier 3: Deterministic / Cached Fallback
        fb = self._cached_fallback(
            question,
            norm_mode,
            rag_bundle,
            as_of_year,
            advisor_fallback_text=advisor_fallback_text,
        )
        latency_ms = (time.monotonic() - t0) * 1000.0
        return {
            "question": question,
            "predicted_answer": fb.get("answer", ""),
            "answer": fb.get("answer", ""),
            "mode": norm_mode,
            "inference_source": "cached_fallback",
            "engine_mode": "CACHED_FALLBACK",
            "model_name": "deterministic_fallback",
            "checkpoint_year": fb.get("checkpoint_year"),
            "benchmark_id": fb.get("benchmark_id"),
            "token_f1_proxy": fb.get("token_f1_proxy"),
            "latency_ms": round(latency_ms, 2),
            "cited_doc_ids": fb.get("cited_doc_ids", []),
            "as_of_year": fb.get("as_of_year"),
            "inferred_category": fb.get("inferred_category"),
            "sources": fb.get("sources", []),
            "source_label": fb.get("source_label", "Cached / Extractive Fallback"),
            "quality_qualified": False,
            "is_advisor_composite": is_advisor_composite,
        }
