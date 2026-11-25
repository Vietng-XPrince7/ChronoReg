"""Hybrid retrieval (BM25 + Dense embeddings via Reciprocal Rank Fusion) for ChronoReg RAG."""
from __future__ import annotations

import math
from typing import Any, Callable, Sequence

EmbedFn = Callable[[list[str]], list[list[float]]]


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Compute cosine similarity between two dense vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    na = math.sqrt(sum(a * a for a in vec_a))
    nb = math.sqrt(sum(b * b for b in vec_b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _hit_unit_key(h: dict[str, Any], fallback_prefix: str, rank: int) -> str:
    """Identify a distinct retrieval unit by chunk_id first (preserving multiple articles per doc), else doc_id."""
    cid = h.get("chunk_id") or h.get("id") or h.get(" chunk", {}).get("chunk_id")
    if not cid and isinstance(h.get("chunk"), dict):
        cid = h["chunk"].get("chunk_id")
    if cid:
        return f"chunk::{cid}"
    did = h.get("metadata", {}).get("doc_id") or h.get("doc_id")
    if did:
        return f"doc::{did}::{str(h.get('document', ''))[:80]}"
    return f"{fallback_prefix}_{rank}"


def reciprocal_rank_fusion(
    bm25_hits: list[dict[str, Any]],
    dense_hits: list[dict[str, Any]],
    k: int = 60,
    bm25_weight: float = 1.0,
    dense_weight: float = 0.6,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """Fuse BM25 and dense ranked hit lists using Reciprocal Rank Fusion (RRF) at chunk granularity."""
    rrf_scores: dict[str, float] = {}
    best_payload: dict[str, dict[str, Any]] = {}
    bm25_raw: dict[str, float] = {}

    for rank, h in enumerate(bm25_hits, 1):
        ukey = _hit_unit_key(h, "bm25", rank)
        rrf_scores[ukey] = rrf_scores.get(ukey, 0.0) + bm25_weight / (k + rank)
        bm25_raw[ukey] = max(bm25_raw.get(ukey, 0.0), float(h.get("score", 0.0)))
        if ukey not in best_payload:
            best_payload[ukey] = dict(h)

    for rank, h in enumerate(dense_hits, 1):
        ukey = _hit_unit_key(h, "dense", rank)
        rrf_scores[ukey] = rrf_scores.get(ukey, 0.0) + dense_weight / (k + rank)
        if ukey not in best_payload:
            best_payload[ukey] = dict(h)

    ordered_keys = sorted(rrf_scores.keys(), key=lambda u: rrf_scores[u], reverse=True)
    fused: list[dict[str, Any]] = []
    for ukey in ordered_keys[:top_k]:
        item = dict(best_payload[ukey])
        item["rrf_score"] = round(rrf_scores[ukey], 6)
        # Keep BM25-compatible score scale for downstream grounding gates
        if ukey in bm25_raw and bm25_raw[ukey] > 0:
            item["score"] = bm25_raw[ukey]
        else:
            item["score"] = round(float(item.get("dense_score", 0.0)) * 30.0, 4)
        fused.append(item)
    return fused


class HybridDenseIndex:
    """Lazy dense vector index over chunks; falls back gracefully when sentence-transformers is absent."""

    def __init__(
        self,
        chunks: Sequence[dict[str, Any]],
        cfg: dict[str, Any] | None = None,
        embed_fn: EmbedFn | None = None,
    ) -> None:
        self._chunks = list(chunks)
        self._cfg = cfg or {"embedding_model": "BAAI/bge-m3"}
        self._embed_fn = embed_fn
        self._vectors: list[list[float]] | None = None
        self._unavailable = False

    def _resolve_embed_fn(self) -> EmbedFn | None:
        if self._embed_fn is not None:
            return self._embed_fn
        if self._unavailable:
            return None
        try:
            from .embedder import embed
            cfg = self._cfg
            return lambda texts: embed(cfg, texts)
        except Exception:
            self._unavailable = True
            return None

    def _ensure_built(self) -> bool:
        if self._vectors is not None:
            return True
        fn = self._resolve_embed_fn()
        if fn is None or not self._chunks:
            self._unavailable = True
            return False
        try:
            texts = [str(c.get("text") or c.get("document") or "")[:2000] for c in self._chunks]
            self._vectors = fn(texts)
            return True
        except Exception:
            self._unavailable = True
            return False

    def query(
        self,
        question: str,
        candidate_indices: list[int] | None = None,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        """Score candidate chunks with cosine similarity at chunk granularity (preserving multi-article hits)."""
        if not self._ensure_built() or self._vectors is None:
            return []
        fn = self._resolve_embed_fn()
        if fn is None:
            return []
        try:
            q_vec = fn([question])[0]
        except Exception:
            return []

        indices = candidate_indices if candidate_indices is not None else list(range(len(self._chunks)))
        scored: list[tuple[float, int]] = []
        for idx in indices:
            if 0 <= idx < len(self._vectors):
                sim = cosine_similarity(q_vec, self._vectors[idx])
                if sim > 0.0:
                    scored.append((sim, idx))
        scored.sort(key=lambda x: x[0], reverse=True)

        hits: list[dict[str, Any]] = []
        seen_chunks: set[str] = set()
        for sim, idx in scored:
            c = self._chunks[idx]
            cid = str(c.get("chunk_id") or c.get("id") or idx)
            if cid in seen_chunks:
                continue
            seen_chunks.add(cid)
            hits.append({
                "id": cid,
                "chunk_id": cid,
                "document": c.get("document", ""),
                "metadata": dict(c.get("metadata", {})),
                "chunk": c,
                "dense_score": round(sim, 6),
                "score": round(sim, 6),
            })
            if len(hits) >= top_k:
                break
        return hits
