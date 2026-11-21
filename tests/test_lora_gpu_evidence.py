"""Protect interpretation of the logged V3 live PEFT smoke evidence.

This checks evidence consistency, not generation quality or GPU functionality.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LORA_DOCS = ROOT / "docs" / "lora"


def test_gpu_evidence_consistent_with_merged_training_manifest():
    sample = json.loads((LORA_DOCS / "V3_LIVE_GPU_SMOKE_2026-11-21.json").read_text(encoding="utf-8"))
    quality = json.loads((LORA_DOCS / "QUALITY_STATUS_2026-11-21.json").read_text(encoding="utf-8"))
    assert sample["status"] == "LIVE_PEFT_SMOKE_PASS_NOT_QUALITY_CERTIFICATION"
    assert sample["engine_mode"] == "LIVE_PEFT_GENERATION"
    assert sample["artifact_integrity"] == "ARTIFACT_INTEGRITY_PASS"
    assert sample["trained_years"] == quality["training_years"]
    assert sample["training_qa"] == quality["training_qa"]
    assert sample["final_adapter_sha256"] == quality["final_adapter_sha256"]
    assert sample["checkpoint_year"] == 2026
    assert sample["requested_year"] == 2025
    assert sample["base_revision_expected"] == "aa8e72537993ba99e69dfaafa59ed015b17504d1"
    assert sample["live_inference_tested"] is True
    assert sample["quality_qualified"] is False
    assert quality["regulation_answer_status"] == "NOT_RELEASED"
    assert sample["model_output"].strip()


def test_notebook_environment_is_not_misrepresented_as_repo_pins():
    sample = json.loads((LORA_DOCS / "V3_LIVE_GPU_SMOKE_2026-11-21.json").read_text(encoding="utf-8"))
    assert sample["versions"]["transformers"] == "4.57.6"
    assert sample["versions"]["peft"] == "0.21.2"
    assert sample["versions"]["bitsandbytes"] == "0.50.2"
    assert sample["versions"]["accelerate"] == "1.15.0"
    assert sample["quality_qualified"] is False
