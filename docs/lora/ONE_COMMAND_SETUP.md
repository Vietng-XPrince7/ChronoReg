# ChronoReg local one-command setup

After this branch is merged and the verified release asset is published:
`git pull origin main`, then `./START_CHRONOREG.ps1` in PowerShell (or
`bash start_chronoreg.sh` in Linux/Ubuntu). Open http://localhost:8000.
Windows prefers an already installed Ubuntu WSL distribution; otherwise
native Python 3.12/3.13 is used. Linux needs uv (unless the environment already exists) and Python 3.12.
Auto mode selects CUDA if `nvidia-smi -L` detects NVIDIA; otherwise it selects
CPU. CUDA needs GCC on Linux and a compatible driver. A 4 GB GPU may still
fail due to available VRAM. If CUDA is detected but unusable, fix it or select
CPU explicitly (`.\START_CHRONOREG.ps1 -Device cpu` or
`bash start_chronoreg.sh --device cpu`). CPU uses the same V3 weights with
FP32 base inference (not NF4); benchmark numerical results may differ.
At least 14 GiB **available** RAM is required before model download/loading;
24 GB or more installed RAM is recommended. WSL guest RAM can be lower than
host RAM. Native Windows CPU may still be blocked by application control;
use WSL2 if needed. CPU is slow and can take minutes per answer; no simulated
answers. Weak machines should use a shared GPU server. CPU/CUDA both reuse
the same `.local_models` artifact cache; explicit CPU has a separate runtime.

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
