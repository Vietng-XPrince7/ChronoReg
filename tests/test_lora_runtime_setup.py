import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from src.lora.runtime_setup import _archive_members, base_files_present, default_models_root, ensure_base_model, install_v3
from src.lora.verified_v3 import ArtifactIntegrityError, from_environment


def _fake_zip(path: Path, *, tamper=False):
    prefix = "chronoreg-fullscope-3b-single-gpu-v3/"
    rows = []
    previous = None
    with zipfile.ZipFile(path, "w") as z:
        for year in range(2022, 2027):
            raw = f"adapter-{year}".encode()
            digest = hashlib.sha256(raw).hexdigest()
            config = {"base_model_name_or_path": "Qwen/Qwen2.5-3B-Instruct", "peft_type": "LORA"}
            stage = {"year": year, "adapter_sha256": digest,
                     "previous_year_adapter_sha256": previous,
                     "data_sha256": hashlib.sha256(str(year).encode()).hexdigest(),
                     "training_rows": 1}
            rows.append(stage)
            z.writestr(f"{prefix}year-{year}/adapter_model.safetensors", b"corrupt" if tamper and year == 2026 else raw)
            z.writestr(f"{prefix}year-{year}/adapter_config.json", json.dumps(config))
            z.writestr(f"{prefix}year-{year}/stage.json", json.dumps(stage))
            previous = digest
        z.writestr(f"{prefix}run_config.json", json.dumps({"model": "Qwen/Qwen2.5-3B-Instruct",
            "years": list(range(2022, 2027)), "checkpoints": rows}))
        z.writestr(f"{prefix}.trainer-2026/unneeded.bin", b"do-not-extract")


def test_install_reuse_minimal(tmp_path):
    archive = tmp_path / "model.zip"
    _fake_zip(archive)
    models = tmp_path / "models"
    first = install_v3(archive, models)
    assert first["status"] == "INSTALLED_AND_SHA_VERIFIED"
    assert len(first["verification"]["checkpoints"]) == 5
    assert not (models / "chronoreg-v3" / ".trainer-2026").exists()
    assert install_v3(archive, models)["status"] == "ALREADY_INSTALLED"
    assert not list(models.glob(".staging*"))


def test_bad_sha_atomic_failure(tmp_path):
    archive = tmp_path / "bad.zip"
    _fake_zip(archive, tamper=True)
    with pytest.raises(ArtifactIntegrityError, match="SHA mismatch"):
        install_v3(archive, tmp_path / "models")
    assert not (tmp_path / "models" / "chronoreg-v3").exists()
    assert not list((tmp_path / "models").glob(".staging*"))


def test_refuse_tampered_existing(tmp_path):
    archive = tmp_path / "model.zip"
    _fake_zip(archive)
    install_v3(archive, tmp_path / "models")
    (tmp_path / "models/chronoreg-v3/year-2026/adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(ArtifactIntegrityError):
        install_v3(archive, tmp_path / "models")


@pytest.mark.parametrize("member", [
    "chronoreg-fullscope-3b-single-gpu-v3/../../evil.txt",
    "/chronoreg-fullscope-3b-single-gpu-v3/run_config.json",
    "chronoreg-fullscope-3b-single-gpu-v3\\run_config.json",
])
def test_reject_unsafe_members(tmp_path, member):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, b"bad")
    with zipfile.ZipFile(path) as z, pytest.raises(ArtifactIntegrityError):
        _archive_members(z)


def test_default_path_and_no_download(tmp_path, monkeypatch):
    monkeypatch.delenv("CHRONOREG_MODELS_ROOT", raising=False)
    assert default_models_root(tmp_path) == tmp_path / ".local_models"
    assert ensure_base_model(tmp_path)["status"] == "BASE_MISSING"


def test_env_points_to_install(tmp_path, monkeypatch):
    archive = tmp_path / "model.zip"
    _fake_zip(archive)
    root = tmp_path / "models"
    install_v3(archive, root)
    base = root / "Qwen2.5-3B-Instruct"
    base.mkdir()
    (base / "config.json").write_text("{}")
    (base / "tokenizer.json").write_text("{}")
    (base / "model-00001-of-00002.safetensors").write_bytes(b"fixture")
    monkeypatch.setenv("CHRONOREG_MODELS_ROOT", str(root))
    monkeypatch.delenv("CHRONOREG_V3_ARTIFACT_DIR", raising=False)
    monkeypatch.delenv("CHRONOREG_BASE_MODEL", raising=False)
    inference = from_environment()
    assert inference.root == root / "chronoreg-v3"
    assert inference.base == base
    assert inference._model is None  # Never loads 3B at import time


def test_partial_base_not_ready(tmp_path):
    base = tmp_path / "Qwen2.5-3B-Instruct"
    base.mkdir()
    (base / "config.json").write_text("{}")
    assert not base_files_present(base)
    assert ensure_base_model(tmp_path)["status"] == "BASE_MISSING"


def test_wrong_local_base_revision_marker_rejected(tmp_path):
    base = tmp_path / "Qwen2.5-3B-Instruct"
    base.mkdir()
    (base / "config.json").write_text("{}")
    (base / "tokenizer.json").write_text("{}")
    (base / "model.safetensors").write_bytes(b"x")
    (base / ".chronoreg_base_revision").write_text("wrong-revision")
    with pytest.raises(ArtifactIntegrityError, match="revision"):
        ensure_base_model(tmp_path)
