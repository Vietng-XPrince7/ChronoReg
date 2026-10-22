# Temporal document registry: data contract and review procedure

## Scope and authority

The **source Markdown is immutable evidence input**, not automatically a legally authoritative record. Its conversion may have omitted annexes, signatures, effective-date clauses or tables. Source links extracted from the Markdown are hints until independently checked.

The registry tracks three separate concepts:

1. **Document identity**: stable ID derived from the Markdown relative path, with a SHA-256 hash of the content. A change to the source text changes the hash but not the ID.
2. **Applicability**: relevant academic year, student cohort, training programme and legal effective interval. These are confirmed only through manual review; the file's `2025/` folder is not proof of a 2025 effective date.
3. **Relationships**: amendments, partial supersessions, full supersessions, citations and same-series associations. Generic mentions of `thay thế` are not enough to identify the replaced document.

A decision issued in February 2024 can govern academic year 2023–2024. A 2026 decision may take effect on signing while first applying to semester I of 2026–2027. These must be represented as distinct fields.

## Working files

| File | Human edited? | Role |
|---|---|---|
| `data/raw/uet/markdown/**/*.md` | No, retain original | Original corpus and reproducible evidence |
| `data/versioning/documents.jsonl` | No | Generated catalog, candidates and verified fields |
| `data/versioning/reviewed_documents.jsonl` | **Yes** | SHA-locked, manual evidence-backed document facts |
| `data/versioning/approved_relations.jsonl` | **Yes** | SHA-locked, manual evidence-backed relationships |
| `data/versioning/relation_review_queue.jsonl` | No | Text snippets for review; cannot be used as approved relations |
| `data/versioning/rag_chunks.jsonl` | No | Reviewed-only chunks for future RAG (empty until review)
| `data/versioning/rag_chunks_draft.jsonl` | No | Opt-in unreviewed chunks for development; never use as the authoritative QA corpus |

The `build` command reads human-edited files but **never overwrites** them. If a reviewed document changes, `build` fails until the human review is revisited. A path-based ID is not a substitute for this hash binding.

## Review a document

1. List candidate files: `py -m src.versioning.cli query --topic tuition --academic-year 2025-2026`.
2. Read the original PDF or official HTML and cross-check the copied Markdown. Check tables, annexes, decision number, signature date and population affected.
3. Generate a template using the exact ID shown by `query`:

   `py -m src.versioning.cli review-template --doc-id <doc_id>`

4. Replace placeholder evidence with the official source URL and page/section. Only fill `issued_date`, `effective_from`, `effective_until_exclusive`, `academic_year`, `scope` and `open_ended_verified` when they are explicitly justified. Keep unknown dates `null`. Put the finished JSON object on one line of `reviewed_documents.jsonl`.
5. Run `py -m src.versioning.cli build` again. Confirm the `verified` count increments.

Example **shape only**, not a claim about any UET decision:

```json
{"doc_id":"uet-example","content_sha256":"exact_current_sha256","review_status":"verified_against_source","evidence_reference":"Official PDF URL, p. 2, art. 5","issued_date":"2025-09-29","effective_from":null,"effective_until_exclusive":null,"academic_year":"2025-2026","scope":"Undergraduates, programme A"}
```

`effective_until_exclusive` is an **exclusive** bound. If a policy is valid through August 31, that field would be September 1, if verified. A null bound means **unknown**, not currently valid. `open_ended_verified=true` requires a documented review and means only that no ending condition was established within the reviewed evidence, not that current laws/sites were rechecked.

## Review a document relationship

Compare the actual source and target PDF/HTML, then issue:

`py -m src.versioning.cli relation-template --from-doc <newer_doc_id> --to-doc <earlier_doc_id> --type amends`

Replace both evidence placeholders and append the JSON object to `approved_relations.jsonl`. Permitted types:

- `references`: new document explicitly cites older document; does **not** mean it replaces it.
- `same_series`: related editions for comparison; does **not** mean replacement.
- `amends`: explicit amendment of a rule/part; requires `applicability_scope`.
- `partially_supersedes`: explicit replacement in a limited scope; requires `applicability_scope`.
- `supersedes`: explicit replacement of the cited document; requires a verbatim evidence quote.

Both endpoint hashes, evidence and review state are mandatory. Self-links, duplicate relations and amendment/supersession cycles are rejected. A replacement of an unidentified group of “previous documents” must remain an **unresolved clue**, not a concrete edge.

## Temporal query contract

`query --as-of 2026-10-22` returns matching **catalog records** with a `temporal_match` label; it does not adjudicate legal validity:

- `inside_verified_interval`: reviewed effective start AND a reviewed end or explicit open-ended evidence; the as-of date fits.
- `outside_verified_interval`: the date is outside a verified interval.
- `unknown_unverified`: date or review status is insufficient.
- `unknown_end_date`: start has been reviewed, but the end is unknown.

When no effective-date evidence exists, the output **does not** silently label the regulation `current`. A future RAG answer must not present the first result in the list as the authoritative valid rule without using these states and the per-rule population scope.

## RAG export and data leakage

`py -m src.versioning.cli export-chunks` exports **only reviewed, scope- and time-annotated policy candidates** with `doc_id`, content hash, character offsets, source URL hint and review status. The raw text can be checked against the Markdown using these offsets. The default export excludes **all unreviewed documents**, plus admissions, non-policy directories, provisional fee notices, scholarship recipient lists and person-level adjustments, to reduce privacy exposure and off-topic noise. With zero verified documents the published chunk count is intentionally zero. For staging/retrieval experiments run `py -m src.versioning.cli export-chunks --include-unreviewed`; that writes **`rag_chunks_draft.jsonl`**, separate from the reviewed output. Never present draft chunks as valid/current policies. This exclusion is a **coarse heuristic**, so review the export before embedding. Use `--include-non-policy --include-unreviewed` only with a deliberate dataset scope and additional privacy checks.

Chunking is currently fixed-width and lossless, not an intelligent legal-article parser. Future retrieval should build article/annex-aware chunks from reviewed text and enforce temporal filters at the rule level.

## Known limits

- Automatic topic, issuing body, document type and academic year are **hints**.
- No official PDF or live website was rechecked during this import.
- Relations require human validation; there are deliberately zero approved relationships in this initial deliverable.
- Year-specific decisions for a particular cohort must not be treated as replacing programmes or cohorts not covered by their scope.
- A document can contain multiple distinct rules and effective intervals; document-level review is not a replacement for rule-level annotation.
- Changes to a website after download require a new source capture/hash and a new review. No live website monitoring is implemented.

## Safe handoff from registry to question answering

`eligible_for_policy_qa` is an automated **topic/kind candidate hint**, not approval. `policy_qa_ready` becomes true only after source-backed manual review supplies nonempty population `scope` and a verified `academic_year` or effective start date. **Even then**, answering an as-of-date question requires an independent `temporal_match` check and checking amendments relevant to that scope; reviewed document metadata alone cannot resolve individual article changes.

Do not embed `rag_chunks_draft.jsonl` as the production/graded truth corpus. Do not treat a missing effective end date as unlimited validity. Preserve original source PDFs for table verification, especially tuition annexes whose Markdown formatting may have broken merged cells.
