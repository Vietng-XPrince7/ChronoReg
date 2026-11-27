# ChronoReg Academic Advisor — portable SLM profile (13.0)

## Windows x64
Prerequisites: Git, Python 3.11+ (with venv/pip), network on first launch and free disk space for the 1.12 GB model and runtime. No CUDA, Ollama, training, API key or administrative install normally required.

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\academic_advisor\start-advisor.ps1
```

The launcher creates a dedicated venv, installs pinned dependencies, verifies and downloads official Qwen2.5-1.5B-Instruct Q4_K_M and llama.cpp Windows x64 CPU binary, starts a loopback inference service and starts StudentHub. The downloads are cached inside the ignored venv. The default endpoint is http://127.0.0.1:8765. Stop with Ctrl+C. Use `-Port 8766` if necessary.

Optional `-Offline` is evidence/tools only, no model. `-Gemini` is opt-in for public documents with your own local API key. The default local model is not the trained LoRA experiment. Its role is source synthesis and additional advisor suggestions; calculations and authoritative clauses are handled by existing tools. Pure LoRA remains a separate experiment and is unavailable in this profile. Do not present these outputs as pure LoRA benchmark results. The UI/API exposes the actual inference source. User-facing address is cô / em.

## Verification
In a second terminal, from repository root:

```powershell
python .\tools\academic_advisor\smoke_slm.py
$env:CHRONOREG_TEST_REPO = (Get-Location).Path
.\.venv-chronoreg-advisor\Scripts\python.exe -m unittest discover -s tools/academic_advisor -p 'test_*.py'
```

The live smoke is a regression check, not a scientific benchmark. Read actual wording and sources. A fallback is not evidence of model inference. Windows download, actual small-model generation and clean-machine deployment require live validation. The model is small; fluent or correct answers to all possible questions are not guaranteed. If a download fails, check the network and retry; do not disable SHA checks. `-Offline` is available explicitly but not equivalent to the SLM experience.

## Windows application-control restriction (13.0 runtime repair)
If Windows refuses llama-server with `0xC0E90002` (or launch policy errors 4551/1260), the launcher attempts the existing independently installed Ollama runtime, imports the same verified 1.5B GGUF under a distinct local tag, and performs a generation probe. No model re-download or changes to Windows security settings. Existing Ollama is optional, not silently installed. If neither permitted runtime is available, startup fails explicitly; `-Offline` (limited tools) or opt-in `-Gemini` remain alternatives. The fallback has not been verified on a fresh Windows machine. It does not use the trained 7B model.

## v14 quality and diagnostics
The SLM advice path reports structured validation failure codes, without logging the generated text or student identifiers. A rejected advice can use one additional model call to select a vetted action; this is labeled as model-selected priority, not free text. Transport failures do not retry. Direct course-credit lookup requires an exact row, program and cohort; unreviewed data remains provisional. The smoke checks the exact curriculum answer and separates natural generation from priority selection. A passing deterministic tool is not evidence of live language generation. A true quality gate still requires live responses and manual review.

## v15 source synthesis
Local SLM uses structured passage references. The server assigns citations and validates numeric claims against the chosen passages, not unrelated retrieved text. The cited passages remain provisional unless reviewed. Duplicate advice is not counted as natural synthesis. This is a regression improvement, not a guarantee of semantic correctness or arbitrary question coverage.

## Runtime cache reliability (15.1)
An existing independently installed Ollama is preferred; its verified 1.5B GGUF is reused. Otherwise llama.cpp is used. Extracted runtime trees are checked against the pinned ZIP and reused without deleting or renaming locked DLLs. Invalid or incomplete trees are retained and a new unique directory is used. Windows security settings are unchanged. If neither local runtime can run, startup reports an error; `-Offline` is explicitly limited.

## Advisor workflows 1.0 (v15.1 compatible)
In Auto, try `Lớp cô có em nào cần gặp riêng? Soạn thông báo cho lớp.` Select a student, then ask `So sánh phương án học lại và soạn tin nhắn riêng cho em này.` The workflow executes local scoped tools, returning `ADVISOR_WORKFLOW` and `workflow_tools` metadata. It ranks support signals (not official eligibility), checks demo grade history against the demo course catalog, and packs candidate retake credit groups at hypothetical budgets (default 6 and 12 credits; override with `tối đa 4 tín chỉ môn nợ`). These are not registration schedules; prerequisites, course availability, verified CPA, and the full official curriculum must be checked. Mixed pass/fail history is withheld from packing pending reconciliation. Message drafts are for teacher review; nothing is sent. Public group drafts never include student identifiers. The existing SLM handles other advisor/knowledge queries; the new computations and drafts are deterministic, not model-generated. Run `python tools/academic_advisor/smoke_workflow.py` in a second terminal for the new live regression. Existing v15.1 gates remain compatible; no new dependencies or model download.

## Advisor workflows 1.1 — provisional prerequisite planning
The exact pinned team-original CNTT 2022–2024 table is used only for the matching demo program and hinted cohort, with explicit unreviewed status. The catalog labels the cohort range as a filename hint, not verified applicability. Publication holds, source hash changes, conflicting rows, missing prerequisite evidence, credit mismatch and unmatched course codes block use of the relevant rows. The planner schedules prerequisites in earlier hypothetical stages and assumes all prior-stage courses pass; it does not assume unknown courses passed or map equivalent codes automatically. No official registration eligibility, complete graduation plan, semester dates or course offerings are inferred. Other programs retain clearly labeled credit-only grouping. In a second terminal run `python tools/academic_advisor/smoke_workflow.py`; the fifth case checks actual ordering, capacity and source metadata.

## Advisor workflows 1.2 — actionable draft reports
In Auto, ask `Lập báo cáo tư vấn cho lớp cô và kế hoạch hành động.` or select a student and ask `Lập phiếu tư vấn cho em này và kế hoạch hành động.` Reports include scoped findings, proposed owners, checkpoints and completion checks. Class report exports are aggregate only; an individual report is private and contains only the selected student. The optional TXT download is performed locally in the browser on a click. Nothing is sent, scheduled or marked complete. Suggested checkpoints are not official deadlines. Existing SLM and other modes are unchanged. The new report workflow is deterministic, not evidence of model generation.
