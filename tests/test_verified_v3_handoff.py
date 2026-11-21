import hashlib
import json
from pathlib import Path
import pytest

from src.lora.verified_v3 import (verify_v3, ArtifactIntegrityError,
                                  VerifiedV3Inference, YEARS)


def _stage(root, *, corrupt=False):
    root.mkdir(exist_ok=True)
    prev = None
    items = []
    for yr in YEARS:
        p = root / f"year-{yr}"
        p.mkdir()
        content = f"fake-weights-{yr}".encode()
        (p / "adapter_model.safetensors").write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        manifest = {"year": yr, "training_rows": 45,
                    "data_sha256": hashlib.sha256(f"dataset-{yr}".encode()).hexdigest(),
                    "adapter_sha256": digest,
                    "previous_year_adapter_sha256": prev}
        (p / "stage.json").write_text(json.dumps(manifest))
        (p / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path":
            "Qwen/Qwen2.5-3B-Instruct", "peft_type": "LORA"}))
        items.append(manifest)
        prev = digest
    (root / "run_config.json").write_text(json.dumps({"model":
        "Qwen/Qwen2.5-3B-Instruct", "years": list(YEARS), "checkpoints": items}))
    return root


def test_v3_manifest_pass(tmp_path):
    result = verify_v3(_stage(tmp_path / "v3"))
    assert result["status"] == "ARTIFACT_INTEGRITY_PASS"
    assert len(result["checkpoints"]) == 5


def test_corrupt_adapter_rejected(tmp_path):
    root = _stage(tmp_path / "v3")
    (root / "year-2026" / "adapter_model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="SHA mismatch"):
        verify_v3(root)


def test_broken_year_chain_rejected(tmp_path):
    root = _stage(tmp_path / "v3")
    path = root / "year-2025" / "stage.json"
    stage = json.loads(path.read_text())
    stage["previous_year_adapter_sha256"] = "0" * 64
    path.write_text(json.dumps(stage))
    with pytest.raises(ArtifactIntegrityError, match="chain mismatch"):
        verify_v3(root)


def test_wrong_base_rejected(tmp_path):
    root = _stage(tmp_path / "v3")
    config = root / "year-2022" / "adapter_config.json"
    config.write_text(json.dumps({"base_model_name_or_path": "not-Qwen", "peft_type": "LORA"}))
    with pytest.raises(ArtifactIntegrityError, match="base model"):
        verify_v3(root)


def test_no_base_model_fails_fast(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing local Qwen"):
        VerifiedV3Inference(_stage(tmp_path / "v3"), tmp_path / "missing")


def test_bad_year_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        VerifiedV3Inference(tmp_path / "missing", tmp_path / "missing", year=2027)
