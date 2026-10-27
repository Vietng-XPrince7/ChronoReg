# LoRA runtime release lock (mainline integration)

The main repository previously allowed `train` with a prepared manifest alone.
That is not safe: the observed local `approved_qa.jsonl` contained 200 legacy
pseudo-approved QA rows, while the 25 V3 reviewed questions were absent.

This patch ports the already tested local fail-closed release guard to Git,
without changing training data, benchmark, adapters, or the evaluation contract.

## Operation

- `train --dry-run` remains available for inspection without loading a model.
- **Live** `train` requires `--release` pointing to a repository-local,
  externally owner-approved dossier. The guard checks SHA-pinned evidence and
  leakage ledgers, candidate provenance, benchmark, curated QA and prepared
  manifest before importing ML dependencies.
- This change **does not issue a release** and does not certify the existing
  25 content approvals as independent human sign-off.
- Existing `src/lora/runs/approved_qa.jsonl` and `prepared/` must not be used
  for live training. Do not create a fake release dossier to satisfy the guard.
- `benchmark_frozen=false` and `training_authorized=false` until separately
  authorized; no evaluation metrics are implied by test passing.

## Review and application

Use `apply_release_lock.py` on the clean `feature/lora-temporal-eval-hardening`
worktree at the exact recorded HEAD. It checks every original source hash,
refuses overwriting any existing release guard/test/docs, and backs up two
modified files to Downloads before writing changes. An idempotent second run
intentionally fails. It never commits or pushes. Run the targeted pytest
suite before staging only the five explicit files and opening a pull request.

This code does not cryptographically verify the actual human reviewer's identity;
only documented release attestations and pinned content can be checked offline.
Release decisions remain the human owner's responsibility.
