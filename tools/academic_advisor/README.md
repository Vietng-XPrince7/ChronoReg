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
