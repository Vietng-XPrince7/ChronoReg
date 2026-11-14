# ChronoReg: LoRA demo handoff, reproducibility and stop gate

## Scope

This contribution is limited to the assigned **Continual LoRA** component. It adds a GPU-free checkpoint verifier and an explicit inference entrypoint. It does NOT alter RAG, evaluation benchmark, training inputs, model hyperparameters, the training release guard, or the existing 5 trained checkpoint files.

## What was proved on the owner's machine (14 November 2026)

- NVIDIA Quadro T1000 under WSL2 Ubuntu: PyTorch 2.9.1+cu126; CUDA available.
- Five local sequential Qwen2.5-0.5B-Instruct adapters, stages 2022–2026, pinned base revision `7ae557604adf67be50417f59c2c2f167def9a775`.
- Training rows reported by demo stage metadata: 5, 5, 4, 5, 5 (24 total). These are not officially released QA.
- Real inference succeeded with `LoRAAnswerer` and year-2026 adapter. **Answer quality was poor**: the AI QH-2025 credits answer was 18 instead of source-reported 135; one response mixed Chinese text, and a historic applicability answer was unsupported.
- Demo ZIP was uploaded to a **DRAFT** GitHub Release (not in main and not public). GitHub asset sha256: `00b4ba473d87b313f03ae099a494a16db8a7c0fd908078a9040f7964093855ab`. The uploader must grant appropriate authorized access or share privately. Do not accidentally publish the draft as a validated model.

## Commands (from repository root)

1. Install Python dependency `PyYAML` in the environment (already part of the project LoRA stack).
2. Check the locally extracted checkpoint chain without loading a model:

```powershell
py -3 -m src.lora.adapter_smoke --repo . --adapter-root 'C:\ChronoReg-Adapters-DEMO\checkpoints' --check-only
```

3. For real GPU inference on the Windows host with Application Control blocking `torch`, use Ubuntu WSL2 and an existing compatible environment:

```bash
cd /mnt/c/HaiAnh/ChronoReg-LoRA-Handoff
PY="$HOME/.local/share/chronoreg-lora/py313/bin/python"
"$PY" -m src.lora.adapter_smoke --repo . \
  --adapter-root /mnt/c/HaiAnh/ChronoReg-LoRA-Demo-Results/checkpoints \
  --year 2026 --as-of-year 2025 --allow-demo \
  --question 'UET là trường đại học nào?'
```

Output labels every result `DEMO_UNRELEASED` with the exact adapter SHA and path. No command here downloads or trains weights. The `--check-only` mode requires no Torch.

## Human-controlled stop gate for the assigned work

**Done in technical demo scope** when (a) tests pass; (b) five checkpoint hashes verified; (c) real WSL inference with explicit adapter is reproducible; (d) code and notes merged after review; (e) another teammate can repeat the check using the separately supplied draft asset.

**NOT done in official research scope** until an independent owner has approved source-backed year-specific training QA, all 90 held-out benchmark cases, the 42 benchmark corrections, the 59 overlap adjudications and the release dossier required by `src/lora/release_guard.py`. Only after that may the existing official five-stage runner execute against a frozen benchmark. Do not create artificial approvals to pass the guard.

**Stop here if those approvals are missing.** Demo results are a scientifically honest baseline, not an accuracy claim. It is not necessary to keep altering prompts or swapping base models to close the demo component.
