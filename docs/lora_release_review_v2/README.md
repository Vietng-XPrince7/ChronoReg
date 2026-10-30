# LoRA release evidence binding v2

## Scope

This patch closes two gaps in the v1 release interlock. A 42-correction ledger is
not full acceptance of the 90-item benchmark. And a 59-row overlap decision CSV
can have the right number of rows while referring to the wrong pairs.

Live training now additionally requires:

1. An independently reviewed, SHA-pinned ledger covering **every benchmark ID**,
   with the exact gold-answer SHA256, source document, source content hash and
   evaluation year bound to each entry.
2. An owner-approved, SHA-pinned freeze manifest that binds the benchmark hash
   to that full review ledger.
3. A SHA-pinned 59-pair inventory, exactly matching every reviewed leakage pair.
   The high-risk `fact-review-2024-026` must be **QUARANTINED**.

All the new example files are **PENDING and NOT APPROVED**. A file that has
checkboxes set to YES is not proof that a qualified human checked the source:
review identity and substantive authorization remain a separate process.

This patch does NOT release data, freeze the benchmark, alter checkpoint weights,
modify the canonical benchmark, or grant training permission.

## Guardrail caveat

The current v1 training guard intentionally expects exactly 24 reviewed QA and
25 decisions; extending the dataset should be designed and reviewed separately.
Never simply bypass this check to train the previous 200 templated records.

## Integration

Use `install_release_evidence_v2.py --repo <path>` for read-only preflight,
then `--apply`. The installer targets an **exact known release_guard.py** and
never alters other files or stages/commits Git changes.

After installation run:

```
py -B -m pytest -p no:cacheprovider -q tests/test_lora_release_lock_v1.py tests/test_lora_release_evidence_binding_v2.py tests/test_lora_pipeline.py tests/test_lora_temporal_eval_contract_v1.py
```

Only the modified release guard and four additive review/test files should
appear in `git status --short`.
