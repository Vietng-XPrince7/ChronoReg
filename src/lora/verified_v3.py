"""Fail-closed real PEFT V3 inference for the ChronoReg research comparison.

No training-answer lookup, benchmark replay, hardcoded policy answers or fuzzy matching.
This is NOT a source of authoritative regulation facts: run a grounded RAG branch
for citations and effective-date questions.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

YEARS = (2022, 2023, 2024, 2025, 2026)
BASE_ID = "Qwen/Qwen2.5-3B-Instruct"
BASE_REVISION = "aa8e72537993ba99e69dfaafa59ed015b17504d1"
SHA_RE = re.compile(r"^[a-f0-9]{64}$")


class ArtifactIntegrityError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            dig.update(chunk)
    return dig.hexdigest()


def verify_v3(root: Path | str, *, require_all_years: bool = True) -> dict:
    """Validate V3 manifest, exact stage hashes, chronological chain and model identity.

    Does not claim the training QA is correct or that model answers are accurate.
    """
    root = Path(root).resolve()
    run_file = root / "run_config.json"
    if not run_file.is_file():
        raise ArtifactIntegrityError(f"Missing run_config.json: {root}")
    run = json.loads(run_file.read_text(encoding="utf-8"))
    if run.get("model") != BASE_ID or run.get("years") != list(YEARS):
        raise ArtifactIntegrityError("Model ID or year order differs from trained V3")
    if run.get("revision") not in (None, BASE_REVISION):
        raise ArtifactIntegrityError("Base revision differs from trained V3")
    checkpoint_rows = run.get("checkpoints", [])
    if len(checkpoint_rows) != len(YEARS):
        raise ArtifactIntegrityError("Expected exactly five checkpoint manifest rows")
    previous_sha = None
    validated = []
    for year, rec in zip(YEARS, checkpoint_rows):
        if rec.get("year") != year:
            raise ArtifactIntegrityError("Checkpoint year order mismatch")
        expected = rec.get("adapter_sha256", "")
        if not SHA_RE.fullmatch(expected):
            raise ArtifactIntegrityError(f"Bad SHA entry for {year}")
        if rec.get("previous_year_adapter_sha256") != previous_sha:
            raise ArtifactIntegrityError(f"Broken year-to-year chain at {year}")
        stage_dir = root / f"year-{year}"
        safetensor = stage_dir / "adapter_model.safetensors"
        cfg_file = stage_dir / "adapter_config.json"
        stage_file = stage_dir / "stage.json"
        if not all(path.is_file() for path in [safetensor, cfg_file, stage_file]):
            raise ArtifactIntegrityError(f"Missing adapter/config/stage file for {year}")
        actual = sha256_file(safetensor)
        if actual != expected:
            raise ArtifactIntegrityError(f"Adapter SHA mismatch for {year}")
        stage = json.loads(stage_file.read_text(encoding="utf-8"))
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        if stage.get("year") != year or stage.get("adapter_sha256") != expected:
            raise ArtifactIntegrityError(f"Stage metadata mismatch for {year}")
        if stage.get("data_sha256") != rec.get("data_sha256"):
            raise ArtifactIntegrityError(f"Training data SHA mismatch for {year}")
        if stage.get("previous_year_adapter_sha256") != previous_sha:
            raise ArtifactIntegrityError(f"Stage chain mismatch for {year}")
        if cfg.get("base_model_name_or_path") != BASE_ID or cfg.get("peft_type") != "LORA":
            raise ArtifactIntegrityError(f"Wrong adapter type or base model for {year}")
        if not isinstance(stage.get("training_rows"), int) or stage["training_rows"] < 1:
            raise ArtifactIntegrityError(f"Invalid training row count {year}")
        validated.append({"year": year, "sha256": actual, "training_rows": stage["training_rows"]})
        previous_sha = expected
    return {"status": "ARTIFACT_INTEGRITY_PASS", "model": BASE_ID,
            "revision": run.get("revision"), "revision_present": bool(run.get("revision")),
            "years": list(YEARS), "checkpoints": validated,
            "scope": "396 curated QA / 53 sources; not full corpus, not quality-certified"}


class VerifiedV3Inference:
    """Loads exact V3 adapter; never falls back to cached answers.

    Require GPU by default for practicality. CPU is available only by explicit opt-in.
    Creating this object does not load a multi-GB base model until generate() is called.
    """

    def __init__(self, artifact_dir: Path | str, base_dir: Path | str,
                 *, year: int = 2026, allow_cpu: bool = False,
                 max_new_tokens: int = 192):
        self.root = Path(artifact_dir).resolve()
        self.base = Path(base_dir).resolve()
        self.year = year
        self.allow_cpu = allow_cpu
        self.max_new_tokens = max_new_tokens
        self._model: Any = None
        self._tok: Any = None
        if year not in YEARS:
            raise ValueError(f"Unsupported checkpoint year {year}")
        self.verified = verify_v3(self.root)
        if not (self.base / "config.json").is_file():
            raise FileNotFoundError(f"Missing local Qwen base config: {self.base}")

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        if not torch.cuda.is_available() and not self.allow_cpu:
            raise RuntimeError("NO_GPU: real QLoRA generation not available; no cached-answer fallback")
        if torch.cuda.is_available() and torch.cuda.device_count() != 1:
            raise RuntimeError("MULTI_GPU: launch with CUDA_VISIBLE_DEVICES=0 before importing torch")
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(str(self.base), local_files_only=True, trust_remote_code=False)
        if tok.pad_token_id is None:
            tok.pad_token = tok.eos_token
        config = {"local_files_only": True, "trust_remote_code": False}
        if device.startswith("cuda"):
            config.update({"device_map": {"": 0}, "dtype": torch.float16,
                           "quantization_config": BitsAndBytesConfig(load_in_4bit=True,
                               bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=torch.float16)})
        else:
            config.update({"dtype": torch.float32, "low_cpu_mem_usage": True})
        base = AutoModelForCausalLM.from_pretrained(str(self.base), **config)
        model = PeftModel.from_pretrained(
            base, str(self.root / f"year-{self.year}"),
            is_trainable=False, local_files_only=True)
        model.eval()
        self._tok, self._model, self._device = tok, model, device

    def generate(self, question: str, *, as_of_year: int | None = None) -> dict:
        question = question.strip()
        if not question:
            raise ValueError("Empty question")
        if as_of_year is not None and as_of_year not in YEARS:
            raise ValueError("as_of_year must be 2022..2026")
        start = time.monotonic()
        self._load()
        import torch
        messages = [
            {"role": "system", "content": (
                "Bạn là nhánh LoRA THỰC NGHIỆM của ChronoReg. Chỉ đưa thông tin khi thực sự biết. "
                "Không bịa số liệu, điều khoản, ngày hiệu lực hay nguồn. Khi không chắc, nói 'Chưa đủ cơ sở xác nhận'. "
                "Nếu yêu cầu giải thích quy trình, phân biệt hướng dẫn chung với quy định bắt buộc.")},
            {"role": "user", "content": (f"Năm được hỏi: {as_of_year}.\n" if as_of_year else "") + question},
        ]
        prompt = self._tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        tokens = self._tok(prompt, return_tensors="pt", add_special_tokens=False)
        if self._device.startswith("cuda"):
            tokens = {key: val.to(self._device) for key, val in tokens.items()}
        with torch.inference_mode():
            output = self._model.generate(**tokens, do_sample=False,
                                          max_new_tokens=self.max_new_tokens,
                                          pad_token_id=self._tok.pad_token_id)
        text = self._tok.decode(output[0][tokens["input_ids"].shape[1]:],
                                skip_special_tokens=True).strip()
        return {"answer": text, "engine_mode": "LIVE_PEFT_GENERATION",
                "checkpoint_year": self.year, "requested_year": as_of_year,
                "has_retrieval_evidence": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 2),
                "source_label": "Experimental QLoRA V3 (no document citation)",
                "reliability": "NOT_QUALIFIED_FOR_AUTHORITATIVE_REGULATIONS"}


def from_environment() -> VerifiedV3Inference:
    """Resolve explicit paths first, otherwise use the verified local install.

    No implicit downloads and no fake-answer fallbacks. A fresh Git clone needs
    the Kaggle adapter installed by scripts/setup_lora_v3.py first.
    """
    repo_root = Path(__file__).resolve().parents[2]
    models_root = Path(os.environ.get("CHRONOREG_MODELS_ROOT", "") or
                       (repo_root / ".local_models")).expanduser().resolve()
    root = os.environ.get("CHRONOREG_V3_ARTIFACT_DIR") or str(models_root / "chronoreg-v3")
    base = os.environ.get("CHRONOREG_BASE_MODEL") or str(models_root / "Qwen2.5-3B-Instruct")
    if not Path(root).is_dir():
        raise RuntimeError("V3 adapter missing. Run python scripts/setup_lora_v3.py --archive <trained-v3.zip>")
    from src.lora.runtime_setup import base_files_present
    if not base_files_present(Path(base)):
        raise RuntimeError("Qwen base incomplete. Run python scripts/setup_lora_v3.py --download-base")
    return VerifiedV3Inference(root, base)
