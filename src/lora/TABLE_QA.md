# Table-derived QA drafts

The paragraph-only draft extractor skips Markdown tables. This module proposes
**additional candidates** from scholarship and tuition tables in reviewed UET
documents. It does not approve a QA pair, alter ingestion/versioning metadata,
or train a model.

## Run

From the repository root:

```powershell
py -m src.versioning.cli build
py -m src.lora.table_candidates
py -m src.lora.cli review-template `
  --candidates src/lora/runs/table_candidates.jsonl `
  --output src/lora/runs/table_review_decisions.jsonl `
  --coverage src/lora/runs/table_review_coverage.csv
```

The second command **refuses to overwrite** an existing `table_candidates.jsonl`;
the third refuses to overwrite existing review decisions. Use an explicit new
`--output` when regenerating candidates after an intentional source update, and
keep existing review files for audit. Generated artifacts remain in ignored
`src/lora/runs/`, not in Git. The original paragraph QA and existing human
reviews are unaffected.

The year is the *start* of the document's verified academic year, not the
adoption date. The module checks the reviewed registry, publication holds,
verified source SHA-256 and exact source row text. Only supported tuition and
scholarship tables are considered. Long/malformed or ambiguous rows are
conservatively skipped; a per-document cap prevents a large table from
silently dominating a single QA batch.

## Human review is required

Every table cell requires independent confirmation against the **original
UET decision/PDF**, including units (per month/credit/year), cohort, degree,
program type, table continuation, merged headers, footnotes, amendment scope
and effective year. The Markdown row alone does not establish all these facts.
If a cell heading is incomplete or a parent label is missing, reject it.

The generated question is intentionally a draft. To approve one, the reviewer
must rewrite the question if necessary, fill actual reviewer/date/note in its
review decision, and use the existing `review-finalize` workflow with the table
candidate and table review file paths. The existing finalizer **requires the
question to be rewritten**; mechanically generated questions should not pass
as human-reviewed by adding a fictitious reviewer. Do not modify
`review_decisions.jsonl` belonging to the paragraph candidates.

Do not train until the data/benchmark owner provides a separate, frozen held-out
benchmark. Exact duplicate checking cannot prove semantic non-overlap between
paraphrases and benchmark questions. The data/benchmark owner also defines the
team's official `as_of_year` interpretation. Benchmark rows must never be
included in training.

## Known limits

- 2022 scholarship/tuition tables may be held because subsequent amendments are
  unresolved. No new source is released by this module.
- Existing 2023 tables supply important *drafts*, but original PDF verification
  is still necessary and the set is not yet suitable for a reported experiment.
- Table extraction is heuristic; multi-level or duplicate headers are skipped
  or may need explicit human contextualization.
- The count of drafts is not a measure of training data quality, coverage,
  temporal accuracy or successful catastrophic-forgetting evaluation.
