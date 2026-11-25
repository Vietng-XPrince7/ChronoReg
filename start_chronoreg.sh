#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PATH="$HOME/.local/bin:$PATH"
# Reuse the existing WSL runtime if it was installed during local troubleshooting.
DEFAULT_ENV="$HOME/chronoreg-env"
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[i]}" == "--device=cpu" ]] || [[ "${args[i]}" == "--device" && "${args[i+1]:-}" == "cpu" ]]; then
    DEFAULT_ENV="$HOME/chronoreg-env-cpu"
  fi
done
ENV_DIR="${CHRONOREG_ENV:-$DEFAULT_ENV}"
if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "Install uv from https://docs.astral.sh/uv/getting-started/installation/ first." >&2
    exit 1
  fi
  uv python install 3.12
  uv venv --python 3.12 "$ENV_DIR"
fi
# CPU-only PyTorch does not need Triton or GCC.
if command -v gcc >/dev/null 2>&1; then
  export CC="${CC:-$(command -v gcc)}"
fi
export CUDA_VISIBLE_DEVICES=0
exec "$ENV_DIR/bin/python" scripts/bootstrap_chronoreg.py "$@"
