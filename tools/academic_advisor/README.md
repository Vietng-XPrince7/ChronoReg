# ChronoReg LoRA-powered Academic Advisor — v12.0

Single cumulative local overlay for ChronoReg main 27b26f2. Stop v11 before starting v12. No retraining, additional model, or dependency. Keep both existing Ollama 7B models. No tracked repository file is modified by this overlay.

## Retained v10 features
- The previous numeric/reference gate accepted a materially incomplete withdrawal answer. v10 does not let generated claims replace source facts. For the complete pinned Article 23 only, the deterministic presenter renders a shorter Vietnamese explanation that retains the deadline for both semester types, refund and late-withdrawal consequences, credit limits, written request/approval and the notice before stopping attendance. Missing markers or multiple articles disable this specialized summary and retain the source text.
- For student/class advice, preserve scoped profile facts, missing-data warning, applicable clause and all roadmap actions. The local LoRA 7B receives anonymized evidence and selects one vetted priority via a small JSON Schema enum. The display uses vetted action wording. This is model-assisted action selection, not unrestricted model-written narrative, and not proof of semantic correctness. Other clause topics retain their source text and add a priority suggestion. Unsupported or malformed output falls back to the first vetted action, explicitly labeled as rule-selected. No inferred independent CPA, official eligibility, actual timetable or invented grades.
- The existing broad knowledge retrieval/synthesis, table readers, conflicting-date handling, temporal and risk gates, and comparison modes are retained. Pure LoRA and Chrono-RAG comparison remain separate. Evidence panel contains original source/profile response. Metadata `advisor_priority.selected_by` identifies whether model or rule selected the action, and `presentation_mode` distinguishes `LORA_ADVISOR_PRIORITY` from `SOURCE_ADVISOR_SUMMARY`.
- `smoke_narrative.py` checks withdrawal completeness as well as real model priority selection; a technical pass is not a full human quality assessment. The complete v9 validator is retained for historical tests but is no longer used to replace SOURCE_CLAUSE or ADVISOR_PLAN facts in the active pipeline.

## Run
```powershell
$repo = 'C:\HaiAnh\ChronoReg-7B-Live-Test'
$fix = 'C:\HaiAnh\ChronoReg-Advisor-v12'
Expand-Archive "$HOME\Downloads\ChronoReg_Academic_Advisor_v12.zip" -DestinationPath $fix -Force
cd $fix
$env:PYTHONUTF8='1'
$env:CHRONOREG_TEST_REPO=$repo
python -m unittest -v test_quality test_scholarship test_runtime test_scope test_tuition test_regulation test_knowledge test_advisor test_narrative test_presentation test_whatif test_conversation test_stage_release
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python run_live.py --repo $repo
```
In another PowerShell:
```powershell
cd 'C:\HaiAnh\ChronoReg-Advisor-v12'
$env:PYTHONUTF8='1'
python smoke_narrative.py --output "$HOME\Downloads\ChronoReg_Advisor_Narrative_v12.jsonl"
```

## Verification and limits
Fixture unit tests: 96 passed, 1 skipped (real router integration), 0 failed. New tests verify complete withdrawal rendering, partial/multiple-article scope, invalid priority, original facts, and anonymized model prompt. Actual Ollama structured response support and action selection are not verified in this environment. v10 does not achieve unrestricted natural reasoning: model selects from vetted actions for source/roster answers, whereas general retrieval synthesis still uses LoRA-generated text. The broader index and roster demo have known data/coverage limitations. No full benchmark or merge approval is implied.

## v11: What-if calculator
- Auto only; GREEN gate required; no attached MSSV. Strict labeled hypothetical inputs. Decimal credit-weighted CPA projection and required future GPA for a target. No official eligibility decisions, no use of GPA alias as independent CPA, no replacement-grade or failed-course scenarios. Pure experiment modes unchanged.
- Calculation metadata identifies deterministic calculator, not LoRA inference. Input values must be explicit. Unrecognized mixed requests retain existing behavior.
- Live check: `python smoke_whatif.py --output "$HOME\Downloads\ChronoReg_WhatIf_v11.jsonl"`
- v11 did not implement browser conversation memory. Real server and UI integration require Windows smoke checks; unit integration tests use a simulated router. No production deployment or merge.

## v12: bounded conversation context and release staging
- Auto UI uses `/api/advisor/chat`. Original `/api/chat` and `/api/compare` are preserved. The API returns a signed, 30-minute context token for a single resolved student or a single-year public query. The browser holds it in memory only; new queries, mode changes, and reloads clear the context. Token is signed, not encrypted, and may contain a demo student ID or previous public question; keep it local. No grades or server-side transcript stored in it.
- Explicit student references (e.g. “em này cần lộ trình gì?”) and narrow year follow-ups (“còn năm 2025 thì sao?”) are supported. Multiple years, missing context and mismatched year/academic-year forms are not inferred. The effective query is audited. Risk gate is checked before and after contextualization; explicit engine modes do not inherit context.
- GPA tích lũy and CPA are accepted aliases for the simulator. Semester GPA remains separate. The demo source's `cpa` alias is not independent evidence of cumulative GPA.
- Live smoke: `python smoke_conversation.py --output "$HOME\Downloads\ChronoReg_Conversation_v12.jsonl"`. Uses two public-year questions, two student questions, an isolated-tab query and the calculator. It does not test all free-form references or browser rendering.
- To prepare for team review only, after live smoke succeeds, use a clean local feature branch and run `python stage_release.py --repo <repo-root>`. This verifies the release manifest and copies files into `tools/academic_advisor` only; no commit/push and no tracked code overwritten. Run from repo root with `python tools/academic_advisor/run_live.py --repo .`. Model weights are still external; both imported 7B models must be available in Ollama. This is an opt-in launcher, not a replacement of the default server. The main branch must be reviewed for compatibility before merge.
- Unit tests: 96 pass, 1 skipped (real router integration). Windows server, actual model inference, full browser behavior and updated main compatibility are not verified by these fixture tests. The research comparison is still separate; this release is the hybrid advisor product, not a LoRA-only result.

## Intelligence 1.5: local advisor action workspace
- Portable home page links to `/advisor/workspace`. Choose a supported goal, preview a data-grounded task plan, then explicitly confirm it. No email, SMS, calendar booking, model call, or official decision is triggered.
- Tasks track proposed due date, owner, completion criteria, status, note, next-review date and up to 20 recent changes shown in the UI. Completion is advisor-reported, not independent verification. Counts describe work completion, not graduation probability.
- SQLite is in the current user's local application data directory (`%LOCALAPPDATA%/ChronoReg/advisor-workspace/<repo-id>/workspace.sqlite3` on Windows). Notes are not encrypted; this is a single-user local demo, not a multi-user production record system. Avoid sensitive notes. Nothing is sent to the LLM or cloud by this workspace.
- One plan per goal per exact roster snapshot. Repeated confirmation is idempotent. Updated or regenerated roster snapshots isolate old plans; no automatic migration or cross-snapshot history browser yet. Existing source and research paths are unchanged.
- `python smoke_workspace.py` probes page, state and three draft goals without saving plans. `python -m unittest -v test_advisor_workspace test_portable` exercises actual API write/read paths with temporary SQLite and synthetic data. Windows and real browser checks still required.

### Intelligence 1.6.0 — opt-in semantic pilot
Set `CHRONOREG_SEMANTIC_PILOT=1` before starting the local-SLM server. Only Auto `/api/advisor/chat` uses this bounded pilot; default off and research/RED routes are unchanged. The planner calls the already installed `qwen3.5:4b-q4_K_M` through loopback Ollama, CPU requested, without sending roster contents to it. It reads the operator question and a short-lived signed structured prior; these input parameters may contain IDs or hypothetical values and the token is signed, not encrypted. Use synthetic demo records only during this pilot. The model is not authorized to issue decisions or modify records. Pilot handles bounded rank/load calculations, single-metric profile lookup/comparison, hypothetical retake schedules including a first-round prerequisite constraint, pinned admission tables and explicit tuition table scope; uncertain/missing facts cause clarification. Other requests still use the legacy route when not selected for the pilot. Current gaps: no general multi-goal executor, no semantic draft/counseling or calendar source adapter, no verified production accuracy or CPU latency guarantee. Stop the server and clear the environment variable to return to legacy 1.5.4 behavior (new revision remains 1.6.0).

### Intelligence 1.6.1 — bounded corrections and tuition units
Single-field corrections with complete prior state bypass the model only when the entire request matches the supported operation. Other requests use the existing semantic planner. Fee unit responses use pinned undergraduate table headers for QH-2023/2024 and do not guess amounts or payment schedules. Pilot remains opt-in and demo-only for acceptance.

### Intelligence 1.6.2 — bounded communication and calendar evidence
The opt-in semantic pilot adds scoped academic invitation drafts, short counseling openings, bounded study schedules, privacy guidance and aggregate internal screening separated from public copy. This adapter is not general-purpose writing: subjects are restricted to neutral academic titles, no roster facts are included in public copy, and no messages are sent. Calendar start lookup requires reviewed chunks with exact academic year, explicit semester and unambiguous start date; absent or ambiguous evidence is not a confirmed date. Fee unit lookup checks populated cells and separates applicable program rows. No training or corpus changes. Continue using demo-only acceptance.

### Intelligence 1.6.11 — streaming transport
Auto chat uses POST /api/advisor/chat/stream (NDJSON), calling the existing protected advisor handler exactly once. Processing heartbeats carry no internal reasoning. The answer is emitted in short chunks only after the existing pipeline completes, then the original response and signed context are returned unchanged. This is progressive delivery of completed text, not raw model-token streaming and not an accuracy upgrade. The old JSON API and explicit research modes remain intact. A disconnected stream is not replayed; the in-flight synchronous inference may continue until it finishes. Use demo data only.

### Advisor Intelligence 1.8.0 — scoped individual missions

The advisor experience supports one private, scoped multi-step individual task: profile overview, meeting preparation, three support priorities, prerequisite-aware retake planning, seven-day self-study plan, and invitation draft. Explicit supported steps use the existing deterministic tools; broad comprehensive preparation can invoke the local Qwen planner to select/order allowed steps. Invalid/unavailable model output falls back to the bounded plan. The model receives the question with eight-digit identifiers masked, not the roster or generated tool results. No cloud calls, writes, message delivery, or official decisions. The signed browser token retains scoped subtask parameters, not a raw transcript or grades. Named revisions can change one artifact without regenerating the others; unresolved prerequisites remain pending. Research/forced model modes are unchanged. Arbitrary multi-student/public missions, arbitrary schedules and unrestricted prose generation are not supported by this module. The existing demo-only data qualification and source holds remain in force.

### Advisor Intelligence 1.8.1 — integrated mission review and revision

Mission synthesis now connects the scoped GPA/debt signals, retake scenario and weekly study budget. It rechecks the pinned curriculum with the existing solver before reporting a simulated schedule; it does not infer a legal credit limit from study time or infer the cause of low grades. Named mission review, read-only scenario comparison and tradeoff advice retain all existing artifact states. Explicit paired retake/study revisions have a strict bounded grammar and update both states only if both succeed. Draft format conversion resolves the destination format rather than the first format mentioned. No sending, writes, training, new dependencies or research-mode changes. Model planning remains bounded; synthesis is deterministic and no free-form legal conclusions are generated.

### Advisor Intelligence 1.8.2 — contextual review
Read-only review views (summary, priority, feasibility, risks, next steps) use current scoped tool facts. A bounded local model may classify unfamiliar review requests; no student records or previous responses are provided to the classifier. No new external actions or policy authority. Explicit requests bypass model. New-session review questions request context.

### Advisor Intelligence 1.9.0 — release candidate

Multi-view assessments use a common read-only evidence summary instead of concatenating separate reviews. Missing self-study time, current schedule, and curriculum/scope checks are explicit. Multi-purpose requests preserve every explicitly recognized review view. Existing source and research gates are unchanged. This is a bounded composer, not unrestricted model generation. Final acceptance requires diverse live questions and independent content review.

### Advisor Intelligence 1.9.2 — release blocker fixes

Explicit admissions method/year wins over inherited slots; unsupported methods are not answered with THPT tables. Simple calendar follow-ups reuse the verified interval tool without model inference. Historical tuition clarification revalidates the adjustment source. No release of held data.

### Scoped review pack (1.9.2)
The separate `data/advisor_sources/reviewed/source_review_20261127.json` contains manually compared factual columns from the UET public pages and notices. It is used for product reference and the existing QH-2022–2024 CNTT dependency planning workflow. The review is not official university approval and does not change research corpus or publication holds. Source bytes, scope, catalog and hold ledger must match at runtime. Missing or modified files fail closed; no automatic old/new course equivalence.

### 1.9.3 scoped source fixes
Scholarship rate lookup uses separate academic-year and cohort dimensions; adds six scoped curriculum summary records for KHMT, HTTT and KTMT. Not approval of archive or entire curriculum.

### 1.9.5
Adds the official 2026–2027 KKHT rate table (25 Nov 2026) with distinct yearly scope; multi-program curriculum comparisons and scoped class-meeting advice. Research data and publication holds are unchanged.

### 1.9.6
Preserves scoped meeting context when transitioning to daily study plans, supports risk review of the resulting mission, filters echoed model-generated questions, and checks the correct QD 3626 provision for award credits and dual-degree GPA thresholds. No source or research ledger changes.

### 1.9.7
Carry actual loaded curriculum evidence through tools instead of upgrading source labels at presentation time. Recompute course-specific study-plan risks and measurable weekly actions; distinguish hypothetical circumstances from confirmed data. Research corpus and review ledgers unchanged.

### 1.9.8
Separate monitoring phrases from edit verbs, student identifiers from numeric word limits, public retake cost from personal planning, and NCKH award synonyms from general graduation ranking. Preserve the scoped mission for neutral private invitation drafting. No new research functionality. Release requires live acceptance and clean integration against main.

### 1.9.9
Fix scoped legacy student-review continuation, public fee estimation and year comparisons, explicit cancellation of a prior topic before a new scholarship request, direct clause references, and neutral public invitation drafting. No new research functionality. Frozen release gate remains mandatory; live model, independent paraphrase review, and full-repository integration are still required.

### 1.9.9.1 (integration maintenance)
Retain conflicting deadlines for explicit institute research-notice overviews, keep pending curricula excluded, and test actual provenance instead of requiring an obsolete label. No model, source pack or research engine changes. Release gate unchanged.

### 2.0.0-pilot (bounded grounded orchestration)
Opt in with `CHRONOREG_GROUNDED_PILOT=1` before starting the portable server. Unset the variable to retain the previous routing paths. The new path grounds explicitly recognized multi-course fee calculations, selected curriculum comparisons, weekly study-plan continuations and the QD 3626 return deadline in the current question and signed context. Existing verified source/roster tools perform all calculations and retrieval. No additional model invocation in the new path; the existing semantic planner remains separate. This is not full model-driven orchestration, does not widen source approval or research modes, and does not certify generalization. Verify the complete frozen release gate and separate transfer cases before merging.
