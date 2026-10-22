"""CLI: python -m src.versioning.cli {build,report,query,export-chunks}."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .core import TOPICS, build, export_chunks, query, read_jsonl


def main() -> None:
    p = argparse.ArgumentParser(description='ChronoReg temporal document registry')
    p.add_argument('--root', type=Path, default=Path('.'), help='ChronoReg repository root')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('build', help='Inventory Markdown and validate any human-reviewed metadata/relations')
    sub.add_parser('report', help='Show the most recently generated coverage report')
    q = sub.add_parser('query', help='List documents with provenance and conservative temporal status')
    q.add_argument('--topic', choices=TOPICS)
    q.add_argument('--academic-year')
    q.add_argument('--folder-year', help='Folder label only; never a validity assertion')
    q.add_argument('--as-of', help='YYYY-MM-DD. Unverified dates are NEVER interpreted as active.')
    template = sub.add_parser('review-template', help='Print a SHA-bound template for a document')
    template.add_argument('--doc-id', required=True)
    relation = sub.add_parser('relation-template', help='Print a SHA-bound relation template; NOT automatically approved')
    relation.add_argument('--from-doc', required=True)
    relation.add_argument('--to-doc', required=True)
    relation.add_argument('--type', required=True, choices=('supersedes','partially_supersedes','amends','references','same_series'))
    chunk = sub.add_parser('export-chunks', help='Export text spans for later RAG ingestion')
    chunk.add_argument('--max-chars', type=int, default=3500)
    chunk.add_argument('--include-non-policy', action='store_true', help='Development only: include non-policy documents in the draft output')
    chunk.add_argument('--include-unreviewed', action='store_true',
                       help='Development only: export candidates separately to rag_chunks_draft.jsonl')
    args = p.parse_args()
    root = args.root.resolve()
    catalog = root / 'data/versioning'
    if args.command == 'build':
        result = build(root)
    elif args.command == 'report':
        path = catalog / 'build_report.json'
        if not path.exists():
            p.error('Run build first')
        result = json.loads(path.read_text(encoding='utf-8'))
    else:
        path = catalog / 'documents.jsonl'
        if not path.exists():
            p.error('Run build first')
        docs = read_jsonl(path)
        if args.command == 'query':
            result = query(docs, topic=args.topic, academic_year=args.academic_year,
                           folder_year=args.folder_year, as_of=args.as_of)
        elif args.command == 'review-template':
            selected = next((d for d in docs if d['doc_id'] == args.doc_id), None)
            if selected is None:
                p.error('Unknown doc ID')
            result = {'doc_id': selected['doc_id'], 'content_sha256': selected['content_sha256'],
                      'review_status': 'verified_against_source', 'evidence_reference': 'REPLACE: PDF/HTML source URL and page/section',
                      'issued_date': None, 'effective_from': None, 'effective_until_exclusive': None,
                      'academic_year': None, 'scope': None, 'open_ended_verified': False}
        elif args.command == 'relation-template':
            index = {d['doc_id']: d for d in docs}
            if args.from_doc not in index or args.to_doc not in index:
                p.error('Unknown document ID')
            result = {'from_doc_id': args.from_doc, 'to_doc_id': args.to_doc,
                      'from_sha256': index[args.from_doc]['content_sha256'],
                      'to_sha256': index[args.to_doc]['content_sha256'],
                      'relation_type': args.type, 'review_status': 'verified_against_source',
                      'evidence_quote': 'REPLACE: verbatim source passage', 'applicability_scope': 'REPLACE: confirmed scope'}
        else:
            if args.include_non_policy and not args.include_unreviewed:
                p.error('--include-non-policy requires --include-unreviewed (draft export only)')
            target = catalog / ('rag_chunks_draft.jsonl' if args.include_unreviewed else 'rag_chunks.jsonl')
            result = {'chunks': export_chunks(docs, root, target, args.max_chars,
                                               args.include_non_policy, args.include_unreviewed),
                      'file': target.as_posix(),
                      'mode': 'draft_unreviewed' if args.include_unreviewed else 'reviewed_only'}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
