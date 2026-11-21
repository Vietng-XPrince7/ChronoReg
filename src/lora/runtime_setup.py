"""Install a verified V3 LoRA ZIP into a deterministic, Git-ignored local cache.

This module never changes the Git tree's tracked data, publishes weights, or
substitutes an answer bank for trained PEFT inference. Artifact integrity is
verified against the training manifest before the install is made visible.
"""
from __future__ import annotations

import os
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from src.lora.verified_v3 import BASE_ID, BASE_REVISION, ArtifactIntegrityError, verify_v3

ARCHIVE_ROOT = "chronoreg-fullscope-3b-single-gpu-v3"
INSTALLED_NAME = "chronoreg-v3"
BASE_NAME = "Qwen2.5-3B-Instruct"
MAX_UNPACKED_BYTES = 320 * 1024 * 1024
NEEDED = {"run_config.json"} | {
    f"year-{year}/{filename}"
    for year in range(2022, 2027)
    for filename in ("adapter_model.safetensors", "adapter_config.json", "stage.json")
}


def default_models_root(repo_root: Path | str) -> Path:
    return Path(os.environ.get("CHRONOREG_MODELS_ROOT", "") or
                (Path(repo_root).resolve() / ".local_models")).expanduser().resolve()


def _archive_members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    found: dict[str, zipfile.ZipInfo] = {}
    aggregate = 0
    for info in zf.infolist():
        name = info.filename
        pp = PurePosixPath(name)
        if (not name or name.startswith("/") or "\\" in name or
            any(component in (".", "..") for component in name.split("/")) or
            pp.parts[0] != ARCHIVE_ROOT or info.flag_bits & 0x1):
            raise ArtifactIntegrityError(f"Unsafe archive member: {name!r}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ArtifactIntegrityError(f"Symlink in model archive: {name!r}")
        aggregate += info.file_size
        if aggregate > MAX_UNPACKED_BYTES:
            raise ArtifactIntegrityError("Artifact archive exceeds unpacked-size limit")
        if info.is_dir():
            continue
        rel = pp.relative_to(ARCHIVE_ROOT).as_posix()
        if rel in NEEDED:
            if rel in found:
                raise ArtifactIntegrityError(f"Duplicate artifact member: {rel}")
            found[rel] = info
    missing = NEEDED - found.keys()
    if missing:
        raise ArtifactIntegrityError(f"Missing artifact members: {', '.join(sorted(missing))}")
    return found


def install_v3(archive: Path | str, models_root: Path | str) -> dict:
    """Verify/extract the minimal inference files; never overwrite an install.

    If the destination exists and passes full SHA verification, reuse it.
    An invalid existing install fails explicitly; it cannot be silently replaced.
    """
    archive = Path(archive).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Missing V3 ZIP: {archive}")
    root = Path(models_root).expanduser().resolve()
    target = root / INSTALLED_NAME
    if target.exists():
        verification = verify_v3(target)
        return {"status": "ALREADY_INSTALLED", "artifact_dir": str(target),
                "verification": verification}
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".staging-chronoreg-v3-{uuid.uuid4().hex}"
    try:
        with zipfile.ZipFile(archive) as zf:
            members = _archive_members(zf)
            temporary.mkdir()
            for relative, info in members.items():
                destination = temporary.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as inp, destination.open("wb") as out:
                    shutil.copyfileobj(inp, out, length=1024 * 1024)
        verification = verify_v3(temporary)
        if target.exists():
            raise FileExistsError(f"Existing model cache appeared during install: {target}")
        temporary.rename(target)
        return {"status": "INSTALLED_AND_SHA_VERIFIED", "artifact_dir": str(target),
                "verification": verification}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def base_files_present(base: Path | str) -> bool:
    """Avoid claiming base-model readiness from a lone config.json file."""
    base = Path(base)
    weights = any(base.glob("*.safetensors")) or any(base.glob("*.bin"))
    tokenizer = (base / "tokenizer.json").is_file() or (base / "vocab.json").is_file()
    return (base / "config.json").is_file() and weights and tokenizer


def ensure_base_model(models_root: Path | str, *, download: bool = False) -> dict:
    """Use a local base, or download the exact revision from the V3 training run."""
    base = Path(models_root).expanduser().resolve() / BASE_NAME
    marker = base / ".chronoreg_base_revision"
    if base_files_present(base):
        recorded = marker.read_text(encoding="ascii").strip() if marker.is_file() else None
        if recorded and recorded != BASE_REVISION:
            raise ArtifactIntegrityError("Local base revision marker does not match trained V3")
        return {"status": "BASE_LOCAL_PRESENT", "base_dir": str(base),
                "base_id": BASE_ID, "expected_revision": BASE_REVISION,
                "revision_verified": recorded == BASE_REVISION}
    if not download:
        return {"status": "BASE_MISSING", "base_dir": str(base),
                "base_id": BASE_ID, "expected_revision": BASE_REVISION,
                "revision_verified": False}
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=BASE_ID, revision=BASE_REVISION, local_dir=str(base))
    if not base_files_present(base):
        raise RuntimeError("Base download did not produce full weights and tokenizer")
    marker.write_text(BASE_REVISION + "\n", encoding="ascii")
    return {"status": "BASE_DOWNLOADED", "base_dir": str(base),
            "base_id": BASE_ID, "expected_revision": BASE_REVISION,
            "revision_verified": True}
