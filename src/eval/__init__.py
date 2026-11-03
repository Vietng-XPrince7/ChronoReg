"""Module đánh giá và đối chuẩn cho hệ thống hỏi đáp quy chế ChronoReg."""
from .evaluator import Evaluator
from .metrics import (
    compute_forgetting_matrix,
    exact_match,
    key_fact_score,
    latency_stats,
    normalize_vietnamese,
    ohr_score,
    temporal_accuracy,
    token_f1,
)

__all__ = [
    "Evaluator",
    "compute_forgetting_matrix",
    "exact_match",
    "key_fact_score",
    "latency_stats",
    "normalize_vietnamese",
    "ohr_score",
    "temporal_accuracy",
    "token_f1",
]

