#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PATH="$HOME/.local/bin:$PATH"
# Reuse the existing WSL runtime if it was installed during local troubleshooting.
ENV_DIR="${CHRONOREG_ENV:-$HOME/chronoreg-env}"
if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "Install uv from https://docs.astral.sh/uv/getting-started/installation/ first." >&2
    exit 1
  fi
  uv python install 3.12
  uv venv --python 3.12 "$ENV_DIR"
fi
if ! command -v gcc >/dev/null 2>&1; then
  echo "Triton requires a C compiler. On Ubuntu: sudo apt update && sudo apt install -y build-essential" >&2
  exit 1
fi
export CC="${CC:-$(command -v gcc)}"
export CUDA_VISIBLE_DEVICES=0
exec "$ENV_DIR/bin/python" scripts/bootstrap_chronoreg.py "$@"
