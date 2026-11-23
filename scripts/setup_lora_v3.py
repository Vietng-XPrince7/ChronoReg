"""Install/check the trained ChronoReg V3 adapter in the local model cache.

Example (Windows):
  python scripts/setup_lora_v3.py --archive "$HOME/Downloads/ChronoReg_LoRA_3B_Trained_V3.zip" --download-base
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.lora.runtime_setup import default_models_root, ensure_base_model, install_v3


def main() -> None:
    p = argparse.ArgumentParser(description="Install SHA-verified V3 adapters and optionally the public Qwen base")
    p.add_argument("--archive", type=Path, help="Trained V3 ZIP from Kaggle; required for initial installation")
    p.add_argument("--models-root", type=Path, default=None, help="Default: <repo>/.local_models")
    p.add_argument("--download-base", action="store_true", help="Explicitly allow HF download of Qwen2.5-3B-Instruct")
    args = p.parse_args()
    root = args.models_root or default_models_root(ROOT)
    target = root / "chronoreg-v3"
    if args.archive:
        adapter = install_v3(args.archive, root)
    else:
        if not target.is_dir():
            p.error("Model not installed: pass --archive /path/to/ChronoReg_LoRA_3B_Trained_V3.zip")
        from src.lora.verified_v3 import verify_v3
        adapter = {"status": "EXISTING_SHA_VERIFIED", "artifact_dir": str(target),
                   "verification": verify_v3(target)}
    base = ensure_base_model(root, download=args.download_base)
    report = {"adapter": adapter, "base": base, "ready_for_gpu_inference":
              base["status"] != "BASE_MISSING", "gpu_inference_tested": False,
              "quality_certified": False}
    if base["status"] == "BASE_MISSING":
        report["next_action"] = "Install Qwen base locally or rerun with --download-base"
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
