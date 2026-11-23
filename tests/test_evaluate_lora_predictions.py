import json
import pytest
from scripts.evaluate_lora_predictions import score


def _jsonl(path, rows):
    path.write_text("".join(json.dumps(v,ensure_ascii=False) + "\n" for v in rows), encoding="utf-8")
    return path


def test_score_exact_and_missing(tmp_path):
    b = _jsonl(tmp_path/'bench', [{"id": "a", "question": "Q1", "gold_answer": "Mức 500 đồng", "type": "active_rule"},
                                  {"id": "b", "question": "Q2", "gold_answer": "A B", "type": "superseded_rule"}])
    pred = _jsonl(tmp_path/'pred', [{"id": "a", "prediction": "mức 500 đồng", "engine_mode": "LIVE_PEFT_GENERATION", "checkpoint_year": 2026}])
    out = score(b,pred)
    assert out['normalized_exact_count'] == 1
    assert out['coverage'] == .5
    assert out['by_category']['superseded_rule']['answered'] == 0


def test_replayed_predictions_rejected(tmp_path):
    b=_jsonl(tmp_path/'b', [{"id": "a", "question": "Q", "gold_answer": "A"}])
    pred=_jsonl(tmp_path/'p', [{"id": "a", "prediction": "A", "engine_mode": "VERIFIED_BENCHMARK_PREDICTION", "checkpoint_year":2026}])
    with pytest.raises(ValueError, match="replayed"):
        score(b,pred)


def test_duplicate_prediction_rejected(tmp_path):
    b=_jsonl(tmp_path/'b', [{"id": "a", "question": "Q", "gold_answer": "A"}])
    one={"id": "a", "prediction": "A", "engine_mode": "LIVE_PEFT_GENERATION", "checkpoint_year":2026}
    pred=_jsonl(tmp_path/'p', [one,one])
    with pytest.raises(ValueError, match="Duplicate"):
        score(b,pred)
