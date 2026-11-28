#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
limited=0
for arg in "$@"; do
  if [[ "$arg" == --offline || "$arg" == --gemini ]]; then limited=1; fi
done
as_root() { if [[ $(id -u) == 0 ]]; then "$@"; else sudo "$@"; fi; }
if ! command -v python3 >/dev/null || ! python3 -c 'import sys,venv,ensurepip; assert sys.version_info >= (3,11)' 2>/dev/null; then
  if ! command -v apt-get >/dev/null; then echo 'Python 3.11+ with venv is required.' >&2; exit 1; fi
  as_root apt-get update
  as_root apt-get install -y python3 python3-venv
fi
python3 -c 'import sys,venv; assert sys.version_info >= (3,11), "Python 3.11+ required; use Ubuntu 24.04+ or install a compatible Python."'
if [[ $limited == 0 ]] && ! command -v ollama >/dev/null; then
  as_root apt-get update
  as_root apt-get install -y curl ca-certificates zstd
  tmp=$(mktemp)
  trap 'rm -f -- "$tmp"' EXIT
  curl --proto '=https' --tlsv1.2 -fL https://ollama.com/install.sh -o "$tmp"
  echo 'Installing Ollama using the official installer; sudo may request your password.'
  sh "$tmp"
  rm -f -- "$tmp"
  trap - EXIT
  command -v ollama >/dev/null || { echo 'Ollama not detected after install.' >&2; exit 1; }
fi
exec python3 "$HERE/team_launch.py" "$@"
