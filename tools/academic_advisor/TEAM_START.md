# Academic Advisor 2.0.0 — one-command startup

From the repository root after cloning or pulling main:

**Windows (CMD or PowerShell):**

```bat
.\tools\academic_advisor\start-advisor.cmd
```

**Ubuntu 24.04+ (x86-64):**

```bash
bash tools/academic_advisor/start-advisor.sh
```

The launcher checks for Python 3.11+ and Ollama, installs missing prerequisites via Windows Package Manager or Ubuntu apt and the official Ollama installer, creates the isolated venv, installs the existing pinned application dependencies, starts Ollama if needed, pulls the required planner only if absent, probes it, verifies the pinned base GGUF and starts the advisor. Both orchestration flags are enabled automatically in the full local profile. No CUDA or API key required. Open http://127.0.0.1:8765 (browser opens automatically when available). Ctrl+C stops the advisor and processes owned by the launcher; independently running services remain running.

First launch needs Internet, a working package manager, installation permission (Windows App Installer / Ubuntu sudo), and sufficient disk/RAM. Recommended 16 GB RAM and at least 15 GB free disk; model sizes and installation requirements can vary. Ubuntu 22.04 requires a separately available Python 3.11+; other platforms are not certified. Existing installations and model tags are reused; the registry tag is not an immutable model hash. No forced upgrades, policy changes or silent offline fallback. If a prerequisite or probe fails, fix the displayed error and rerun. `--offline` / `-Offline` and `--gemini` / `-Gemini` are explicitly limited profiles, not the accepted local profile. `--no-browser` / `-NoBrowser` can be used for headless startup. Windows options use PowerShell syntax, Ubuntu options use long CLI flags.

The roster is sample data, not an official student information system. Research modes and source holds remain separate. The launcher's actual cross-platform fresh-machine installation must be verified before claiming universal compatibility.

## Final release verification

From the repository root, after the launcher has prepared the environment:

Windows PowerShell:

```powershell
$env:CHRONOREG_TEST_REPO = (Get-Location).Path
.\.venv-chronoreg-advisor\Scripts\python.exe -m unittest discover -s tools/academic_advisor -p 'test_*.py'
.\.venv-chronoreg-advisor\Scripts\python.exe tools/academic_advisor/smoke_experience.py --demo-only --output "$HOME\Downloads\ChronoReg_Release_Live.json"
```

Run the second command while the full local server is running. Ubuntu: use the launcher-created `.venv-chronoreg-advisor/bin/python` and export `CHRONOREG_TEST_REPO="$PWD"`; choose a local output path. Smoke output contains technical checks rather than a scientific benchmark. Do not publish demo student data, logs, local caches, credentials or model weights.

## Historical deployment notes (superseded where startup differs)

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

## Advisor Intelligence 1.0 — answer quality
This update targets the Advisor Auto conversation only, based on the eight-turn manual review. It separates direct legal questions from class analytics, uses the verified Article 21/23 limits for explicit semester-GPA cases, and does not apply the main-semester limit to summer terms. The new local task planner resolves explicit review, class priorities, course-history and strategy goals; on ambiguous in-scope open requests, the SLM may select one of a limited set of goal IDs. It cannot choose student IDs or create new tool parameters. Scoped tools compute facts, prerequisite candidates, and action plans. The system does not infer official eligibility or current graduation risk from stale demo data. Unreviewed curricula remain provisional. Numeric/source checks do not establish semantic correctness. The old RAG/LoRA research dispatch and model/runtime are unchanged. Auto mode suppresses duplicate roadmap panels only for the new compact goal responses.

From the repository root, with the local-SLM server running, run `python tools/academic_advisor/smoke_intelligence.py --full` (all tests, old workflow suite and 12 focused live cases). Add `--show-demo` only for the demo roster to print the actual answer text for manual quality review. The earlier Handoff Gate pins the previous release and is not valid for this revised manifest. A passing focused suite is not a blind benchmark or proof of unrestricted tool calling.

### Advisor Intelligence 1.1
Scope rejection precedes record task planning; same-tier triage is by known debt descending, then semester GPA ascending and conduct score ascending (not official risk). Improvement and graduation strategies are distinct. Comprehensive individual review compares hypothetical 6 and 12 retake-credit caps without claiming a registration limit or optimal plan. Run `python tools/academic_advisor/smoke_intelligence.py --full --show-demo` against the restarted local-SLM server.

### Intelligence 1.3 — adaptive counseling
The local SLM may choose the meeting-preparation tool for ambiguous scoped support requests, then draft one or two open questions and select one bounded support action. No raw roster or numerical student facts are sent to the planner; the existing facts and scope checks remain authoritative. Model failure falls back to deterministic counseling. The live probe reports REVIEW if no valid model contribution is received. This is a focused acceptance check, not a blind benchmark.

### Intelligence 1.4 — focused counseling and exact candidate planning
Auto conversation retains coarse hypothetical counseling topics in signed, short-lived context (not encrypted, not a record or verified fact). Explicit corrections remove topics; a change of student, a fresh tab, or a non-advisor mode does not carry them over. Focused follow-ups and requested question counts avoid repeating the intake. The local SLM remains bounded and malformed advisor-to-student questions are rejected. Candidate prerequisite plans use exact minimum-round search for up to 12 reachable, matched courses; larger cases retain the safe heuristic. Excluded courses, provisional curriculum status, unknown course offerings and official load restrictions remain unchanged. No new model, external API or data changes. The focused test suite and the live smoke are regression checks; do not treat them as blinded evaluation.
