#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${CHRONOREG_PYTHON:-$HOME/.local/share/chronoreg-lora/py313/bin/python}"
ADAPTER_ROOT="${CHRONOREG_ADAPTER_ROOT:-/mnt/c/HaiAnh/ChronoReg-LoRA-Demo-Results/checkpoints}"
if [[ ! -x "$PY" ]]; then echo "Missing WSL Python: $PY" >&2; exit 2; fi
cd "$REPO"
"$PY" -m src.lora.adapter_smoke --repo "$REPO" --adapter-root "$ADAPTER_ROOT" --check-only
"$PY" -m src.lora.adapter_smoke --repo "$REPO" --adapter-root "$ADAPTER_ROOT" \
  --year 2026 --as-of-year 2025 --allow-demo \
  --question 'UET là trường đại học nào? Trực thuộc đại học nào?'
