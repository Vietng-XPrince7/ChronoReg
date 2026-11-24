# LoRA V3 web startup

One resident verified V3 (year-2026) model per server process. FastAPI lifespan preloads it before serving requests. The legacy chat/compare and experimental answer-v2 use the same runtime. No prediction bank, training answer lookup or hard-coded procedural fallback is used by those endpoints. Existing router and RED gate are unchanged; live LoRA output is experimental and not qualified as official regulations. The underlying legacy engine is retained for other consumers, not instantiated by StudentHub.

## One-time installation on each machine (if not already installed)

```powershell
python scripts/setup_lora_v3.py --archive "$HOME\Downloads\ChronoReg_LoRA_3B_Trained_V3.zip" --download-base
```

The supplied V3 archive must be present; the setup script verifies adapter SHA and downloads the pinned Qwen base on explicit request. Default local paths: `.local_models/chronoreg-v3` and `.local_models/Qwen2.5-3B-Instruct`. Alternative paths are supported by the existing `CHRONOREG_MODELS_ROOT`, `CHRONOREG_V3_ARTIFACT_DIR`, `CHRONOREG_BASE_MODEL` configuration. GPU and compatible torch/transformers/PEFT/bitsandbytes installation are necessary. Do not download on every startup.

## Every server launch

```powershell
$env:CUDA_VISIBLE_DEVICES = "0"
python -m uvicorn src.api.studenthub_server:app --host 127.0.0.1 --port 8000 --workers 1
```

Use one worker, without `--reload` for stable GPU residency. Opening another tab or refreshing does not reload the model. Restarting the process reloads weights automatically. Check `http://127.0.0.1:8000/api/lora/status` for `READY` and `ready: true`. If unavailable, the server remains accessible and the LoRA endpoints report unavailable; check log, fix the local installation and restart. A ready state indicates successful loading, not accuracy certification. Test real inference through `/api/chat` with `force_engine: continual_lora` or research comparison, checking `engine_mode: LIVE_PEFT_GENERATION`. A startup smoke with fake model in tests does not establish GPU inference.
