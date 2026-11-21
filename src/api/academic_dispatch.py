"""Opt-in bridge for /api/answer-v2; existing RAG and StudentHub APIs remain unchanged."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.router.evidence_selector import Candidate, HybridDispatch
from src.router.source_verifier import SourceVerifier


@lru_cache(maxsize=1)
def _v3():
    from src.lora.verified_v3 import from_environment
    return from_environment()


def build_dispatch(repo_root: Path, rag_predictor):
    """rag_predictor(question) returns existing RAG pred dict; independent dependency injection."""
    verifier = SourceVerifier(repo_root)

    def run_rag(question: str) -> Candidate:
        prediction = rag_predictor(question)
        ids = tuple(prediction.get("cited_doc_ids") or [])
        proof = verifier.check(ids, question)
        raw = prediction.get("predicted_answer") or prediction.get("answer") or ""
        # Do not conflate citation integrity with semantic correctness.
        return Candidate(engine="chrono_rag", answer=raw,
            engine_mode="RETRIEVED", cited_doc_ids=ids,
            evidence_verified=proof["sha_verified"],
            effective_year_verified=proof["year_verified"],
            answer_entailment_verified=False)

    def run_lora(question: str) -> Candidate:
        result = _v3().generate(question)
        return Candidate(engine="continual_lora", answer=result["answer"],
                         engine_mode=result["engine_mode"])

    return HybridDispatch(rag_runner=run_rag, lora_runner=run_lora)
