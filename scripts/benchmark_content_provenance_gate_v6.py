#!/usr/bin/env python3
"""Read-only amount and Markdown-lineage audit for a 90-item ChronoReg benchmark.

This gate only detects reproducible numeric provenance gaps. It cannot authorize
fact signoff, benchmark freeze, or training.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

EXPECTED_BENCHMARK_SHA256 = '333404a93e510ca580a19dc149c2f93587782eb6380def40626deaa05e1036e2'
AMOUNT = re.compile(r'(?<!\d)\d{1,3}(?:\.\d{3})+(?!\d)')


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_references(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        data = list(csv.DictReader(stream))
    if len(data) != 22 or len({r['doc_id'] for r in data}) != 22:
        raise ValueError('Expected exactly 22 unique source registry documents.')
    if len({r['source_sha256'] for r in data}) != 22:
        raise ValueError('Expected 22 unique source SHA-256 values.')
    return data


def read_benchmark(repo: Path):
    path = repo / 'data/qa_benchmark/benchmark.jsonl'
    content = path.read_bytes()
    if checksum(content) != EXPECTED_BENCHMARK_SHA256:
        raise ValueError('Canonical benchmark hash differs; stop before reviewing a new version.')
    data = [json.loads(line) for line in content.decode('utf-8-sig').splitlines() if line.strip()]
    if len(data) != 90 or len({r['id'] for r in data}) != 90:
        raise ValueError('Expected 90 unique canonical benchmark IDs.')
    return data


def load_sources(repo: Path, references):
    root = repo.resolve(strict=True)
    by_sha = {}
    for item in references:
        relative = Path(item['local_paths'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe source path in registry: ' + str(relative))
        path = repo / relative
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('Source path escapes repo or is symlinked: ' + str(relative))
        blob = path.read_bytes()
        actual = checksum(blob)
        if actual != item['source_sha256']:
            raise ValueError('Source SHA-256 mismatch: ' + item['doc_id'])
        by_sha[actual] = blob.decode('utf-8-sig')
    return by_sha


def audit_rows(rows, sources):
    result = []
    for row in rows:
        source_sha = row['source_sha256']
        if source_sha not in sources:
            raise ValueError('Benchmark points to unregistered source: ' + row['id'])
        amounts = list(dict.fromkeys(AMOUNT.findall(row['gold_answer'])))
        absent = [v for v in amounts if v not in sources[source_sha]]
        supplementary = {value: sorted(h for h, body in sources.items() if h != source_sha and value in body)
                         for value in absent}
        status = ('ALL_GOLD_AMOUNTS_IN_PRIMARY_SOURCE_OR_NO_AMOUNT' if not absent else
                  'NEEDS_MULTIPLE_DOCUMENTS' if all(supplementary.values()) else
                  'UNSUPPORTED_AMOUNT_IN_22_SOURCE_SET')
        result.append({'benchmark_id': row['id'], 'gold_amounts': amounts,
                       'missing_primary_amounts': absent,
                       'supplemental_source_sha256': supplementary,
                       'status': status,
                       'semantic_review': 'NOT_AUTOMATED'})
    return result


def run(repo: Path, ref: Path):
    rows = read_benchmark(repo)
    references = read_references(ref)
    docs = load_sources(repo, references)
    audited = audit_rows(rows, docs)
    flagged = [item for item in audited if item['missing_primary_amounts']]
    output = {
        'status': 'REVIEW_REQUIRED', 'benchmark_frozen': False,
        'training_authorized': False,
        'scope': 'Verified Markdown bytes and verbatim VND amount strings only; not factual truth or original PDF authentication',
        'benchmark_sha256': EXPECTED_BENCHMARK_SHA256, 'benchmark_rows': len(rows),
        'source_documents_sha_verified': len(docs),
        'amount_provenance_exceptions': len(flagged),
        'flagged': flagged,
    }
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', required=True, type=Path)
    ap.add_argument('--registry', type=Path)
    args = ap.parse_args()
    registry = args.registry or (args.repo/'docs/benchmark_review_v6/source_metadata_reference_22.csv')
    try:
        output = run(args.repo, registry)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as err:
        print(json.dumps({'status': 'INVALID_INPUT', 'error': str(err)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 2  # Remains blocked even after every amount is present; owner review is mandatory.


if __name__ == '__main__':
    sys.exit(main())
