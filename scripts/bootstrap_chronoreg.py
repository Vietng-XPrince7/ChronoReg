"""One-time install, verified local artifacts, then one web worker."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.lora.runtime_setup import (
    ARCHIVE_ROOT, NEEDED, BASE_NAME, default_models_root, ensure_base_model, install_v3,
)
from src.lora.verified_v3 import BASE_REVISION, verify_v3

ASSET = "ChronoReg_LoRA_3B_V3_Inference.zip"
RELEASE_URL = ("https://github.com/Vietng-XPrince7/ChronoReg/releases/download/"
               "lora-v3-inference-20261124/" + ASSET)
CHECKPOINTS = (
    "4bfd1f7f0b8ca9bb651a70fcb64157ada63703fcca4dec4c0d4d061705ca4815",
    "ee58b81396e5d54956e781cfc1988e7c7ce047c06567e33293b2c19eec6bb8b1",
    "3cfd9cc77a59a6903a5f707c5875ac5f892c4244fd12fa2ab2b2160bcad1a645",
    "75778b4916b7c7e3f3c76ba9e8711ad963696787008d4c9b7d8a536b5e3c6ba5",
    "8fa4bb0436b96d9a6512d38b240b7f28c854d776c6db7d618efea4feee6ad24a",
)
PACKAGES = {
    "transformers": "4.51.3", "peft": "0.15.2", "accelerate": "1.6.0",
    "bitsandbytes": "0.48.2", "huggingface_hub": "0.34.4",
    "fastapi": "0.115.12", "uvicorn": "0.34.2", "pydantic": "2.11.4",
    "pyyaml": "6.0.2", "numpy": "2.2.6", "pandas": "2.2.3",
    "httpx": "0.28.1", "sentence-transformers": "3.4.1",
}
MAX_DOWNLOAD = 320 * 1024 * 1024

def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)

def version(name):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None

def pip(*args):
    if version("pip"):
        run(sys.executable, "-m", "pip", "install", *args)
    elif shutil.which("uv"):
        run("uv", "pip", "install", "--python", sys.executable, *args)
    else:
        raise RuntimeError("pip/uv missing from runtime environment")

def ensure_deps():
    if version("torch") != "2.7.1+cu126":
        pip("torch==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu126")
    # Reuse compatible installed packages; exact pins keep new installs reproducible.
    missing = [f"{k}=={v}" for k,v in PACKAGES.items() if version(k) != v]
    if missing:
        pip(*missing)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="0")
    code = ("import torch,transformers,peft,bitsandbytes,accelerate,fastapi,uvicorn;"
            "assert torch.cuda.is_available(), 'CUDA unavailable';"
            "assert torch.cuda.device_count()==1, 'Expected one visible GPU';"
            "print('CUDA_READY',torch.cuda.get_device_name(0),"
            "torch.cuda.get_device_properties(0).total_memory//(1024**2),'MiB')")
    subprocess.run([sys.executable,"-c",code], env=env, cwd=ROOT, check=True)

def verify_exact(adapter):
    report = verify_v3(adapter)
    if tuple(x["sha256"] for x in report["checkpoints"]) != CHECKPOINTS:
        raise RuntimeError("Adapter is not the approved five V3 checkpoints")
    if report["revision"] != BASE_REVISION:
        raise RuntimeError("Wrong/missing pinned Qwen revision")
    return report

def archive_from_cache(models, output):
    adapter = models / "chronoreg-v3"
    verify_exact(adapter)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Only inference metadata and weights. Never include training samples/logs.
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for rel in sorted(NEEDED):
            z.write(adapter / rel, f"{ARCHIVE_ROOT}/{rel}")
    digest = hashlib.sha256()
    with output.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            digest.update(chunk)
    print("RELEASE_ASSET_READY", output, "SHA256", digest.hexdigest(), flush=True)

def download_archive(dest):
    print("Downloading verified V3 release asset once...", flush=True)
    req = urllib.request.Request(RELEASE_URL, headers={"User-Agent":"ChronoReg-bootstrap/1"})
    with urllib.request.urlopen(req, timeout=60) as response, dest.open("xb") as f:
        count = 0
        for data in iter(lambda: response.read(1024*1024), b""):
            count += len(data)
            if count > MAX_DOWNLOAD:
                raise RuntimeError("Release asset exceeds expected size limit")
            f.write(data)

def ensure_adapter(models, explicit_archive=None):
    target = models / "chronoreg-v3"
    if target.exists():
        verify_exact(target)
        print("V3_CACHE_REUSED", flush=True)
        return
    models.mkdir(parents=True, exist_ok=True)
    candidates = [explicit_archive] if explicit_archive else [
        Path.home() / "Downloads" / "ChronoReg_LoRA_3B_Trained_V3.zip",
        ROOT / ".local_models" / ASSET,
    ]
    for path in candidates:
        if path is not None and path.is_file():
            with tempfile.TemporaryDirectory(dir=models) as d:
                stage = Path(d)
                install_v3(path, stage)
                verify_exact(stage / "chronoreg-v3")
                (stage / "chronoreg-v3").rename(target)
            print("V3_INSTALLED_FROM_LOCAL_ARCHIVE", flush=True)
            return
    if explicit_archive:
        raise FileNotFoundError(explicit_archive)
    with tempfile.TemporaryDirectory(dir=models) as d:
        stage = Path(d)
        archive = stage / ASSET
        try:
            download_archive(archive)
        except Exception as exc:
            raise RuntimeError("V3 release not accessible. Ask project maintainer to publish "
                               "the inference asset, or pass --archive PATH.") from exc
        install_v3(archive, stage)
        verify_exact(stage / "chronoreg-v3")
        (stage / "chronoreg-v3").rename(target)
    print("V3_DOWNLOADED_AND_VERIFIED", flush=True)

def ensure_base(models):
    base = models / BASE_NAME
    info = ensure_base_model(models, download=True)
    if not info["revision_verified"]:
        raise RuntimeError("Existing base has no verified revision marker; inspect it before reuse")
    index = base / "model.safetensors.index.json"
    if index.exists():
        shards = set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())
        if not shards or not all((base / p).is_file() and (base / p).stat().st_size > 0 for p in shards):
            raise RuntimeError("Local Qwen shard set incomplete; do not start until repaired")
    print(info["status"], flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--archive", type=Path)
    p.add_argument("--models-root", type=Path)
    p.add_argument("--package-release", type=Path)
    p.add_argument("--setup-only", action="store_true")
    p.add_argument("--rebuild-rag", action="store_true")
    args = p.parse_args()
    models = (args.models_root or default_models_root(ROOT)).expanduser().resolve()
    if args.package_release:
        archive_from_cache(models, args.package_release)
        return
    if sys.version_info[:2] not in ((3,12),(3,13)):
        raise RuntimeError("Use Python 3.12 or 3.13 for the pinned runtime")
    if not (ROOT / "src/lora/web_runtime.py").is_file():
        raise RuntimeError("LoRA autoload changes not present in this checkout")
    ensure_deps()
    ensure_adapter(models, args.archive)
    ensure_base(models)
    if args.rebuild_rag or not (ROOT/"data/versioning/documents.jsonl").is_file():
        run(sys.executable, "-m", "src.versioning.cli", "build")
    if not (ROOT/"data/versioning/documents.jsonl").is_file():
        raise RuntimeError("RAG registry missing after build")
    print("SETUP_PASS: GPU detected; artifacts verified; live inference not yet tested", flush=True)
    if args.setup_only:
        return
    os.environ["CHRONOREG_MODELS_ROOT"] = str(models)
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ.pop("CHRONOREG_V3_ARTIFACT_DIR", None)
    os.environ.pop("CHRONOREG_BASE_MODEL", None)
    os.environ.pop("QWEN_MODEL_DIR", None)
    run(sys.executable, "-m", "uvicorn", "src.api.studenthub_server:app",
        "--host", "127.0.0.1", "--port", "8000", "--workers", "1")

if __name__ == "__main__":
    main()
