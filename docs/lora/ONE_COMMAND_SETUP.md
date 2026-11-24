# ChronoReg local one-command setup

After this branch is merged and the verified release asset is published:
`git pull origin main`, then `./START_CHRONOREG.ps1` in PowerShell (or
`bash start_chronoreg.sh` in Linux/Ubuntu). Open http://localhost:8000.
Windows prefers an already installed Ubuntu WSL distribution; otherwise
native Python 3.12/3.13 is used. Linux needs uv (unless the environment
already exists), Python 3.12 and GCC. A working NVIDIA CUDA GPU is required.
A 4 GB GPU may still fail due to available VRAM; no simulated answers.

Model files live in `.local_models`, not Git. Qwen is downloaded at the
pinned revision, V3 is downloaded from the fixed release URL only if no
valid local adapter exists. All five trained checkpoint hashes are pinned.
First run needs internet and disk space (allow 15–20 GB including runtime).
The same environment and weights are reused on subsequent runs. A server
restart reloads the model into memory; a browser refresh does not.

For maintainers only: the repository is public. Review redistribution
permissions before uploading; create a minimal inference-only ZIP from an
already verified local cache with:
`python scripts/bootstrap_chronoreg.py --package-release ChronoReg_LoRA_3B_V3_Inference.zip`
Then publish exactly that asset under release tag `lora-v3-inference-20261124`.
Do not publish raw QA/training logs. No credentials are stored in code.

Check `/api/lora/status`: READY means real weights loaded, not accuracy
certified. Test actual `/api/chat` inference separately. Setup errors are
explicit; no answer-bank fallback. The registry is generated if missing;
use `-RebuildRag` (Windows) or `--rebuild-rag` (Linux) to rebuild on demand.
The separate training requirements are untouched.
